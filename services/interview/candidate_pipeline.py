import json
from typing import Any, List

from bson import ObjectId
from litellm import completion

from services.config import GEN_MODEL
from services.db import candidate_profiles, generated_questions
from services.interview.models import GeneratedQuestionSet
from services.interview.question_bank import is_too_similar, retrieve_seed_questions


def _dedupe_strings(values: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        normalized = cleaned.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(cleaned)
    return deduped


def _flatten_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        values: List[str] = []
        for item in value:
            values.extend(_flatten_strings(item))
        return values
    if isinstance(value, dict):
        values: List[str] = []
        for item in value.values():
            values.extend(_flatten_strings(item))
        return values
    return []


def _string_from_object(obj: Any, preferred_keys: List[str]) -> str:
    if isinstance(obj, str):
        return obj.strip()
    if not isinstance(obj, dict):
        return ""
    for key in preferred_keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_candidate_profile(user_id: str) -> dict:
    if not user_id:
        raise ValueError("user_id is required.")

    filters = [{"userId": user_id}, {"_id": user_id}]
    if ObjectId.is_valid(user_id):
        object_id = ObjectId(user_id)
        filters.insert(0, {"userId": object_id})
        filters.insert(1, {"_id": object_id})

    candidate = candidate_profiles.find_one(
        {"$or": filters},
        sort=[("updatedAt", -1), ("createdAt", -1)],
    )
    if not candidate:
        raise ValueError(f"No candidate profile found for user_id '{user_id}'.")
    return candidate


def _extract_preferred_roles(profile: dict) -> List[str]:
    intro = profile.get("introductionQuestions") or {}
    roles = intro.get("preferredRoles") or []
    values = [
        _string_from_object(role, ["role", "name", "title", "label", "value"])
        for role in roles
    ]
    return _dedupe_strings([value for value in values if value])


def _extract_candidate_skills(profile: dict) -> List[str]:
    intro = profile.get("introductionQuestions") or {}

    raw_values: List[str] = []
    raw_values.extend(_flatten_strings(intro.get("favoriteTechnology")))

    for achievement in profile.get("achievements") or []:
        if not isinstance(achievement, dict):
            raw_values.extend(_flatten_strings(achievement))
            continue
        for key, value in achievement.items():
            key_lower = key.lower()
            if "soft" in key_lower:
                continue
            if "technical" in key_lower or "skill" in key_lower or "tech" in key_lower:
                raw_values.extend(_flatten_strings(value))

    tech_key_tokens = ("tech", "skill", "stack", "tool", "framework", "database", "language")
    for section_name in ["projects", "workExperiences"]:
        for item in profile.get(section_name) or []:
            if not isinstance(item, dict):
                raw_values.extend(_flatten_strings(item))
                continue
            for key, value in item.items():
                if any(token in key.lower() for token in tech_key_tokens):
                    raw_values.extend(_flatten_strings(value))

    return _dedupe_strings(raw_values)


def _extract_soft_skills(profile: dict) -> List[str]:
    values: List[str] = []
    for achievement in profile.get("achievements") or []:
        if not isinstance(achievement, dict):
            continue
        values.extend(_flatten_strings(achievement.get("softSkills")))
    return _dedupe_strings(values)


def _extract_advantage_points(profile: dict) -> List[str]:
    values: List[str] = []
    for achievement in profile.get("achievements") or []:
        if not isinstance(achievement, dict):
            continue
        values.extend(_flatten_strings(achievement.get("advantagePoint")))
    return _dedupe_strings(values)


def _infer_candidate_level(profile: dict) -> str:
    academic_info = profile.get("academicInfo") or {}
    work_experiences = profile.get("workExperiences") or []
    graduation_year = academic_info.get("graduationYear")

    if len(work_experiences) >= 4:
        return "Senior"
    if len(work_experiences) >= 2:
        return "Mid"
    if len(work_experiences) >= 1:
        return "Junior"
    if isinstance(graduation_year, int) and graduation_year >= 2026:
        return "Intern"
    return "Fresher"


def _infer_question_category(preferred_roles: List[str], skills: List[str]) -> str:
    category_hints = preferred_roles + skills
    keyword_map = {
        "frontend": "Frontend",
        "front end": "Frontend",
        "react": "Frontend",
        "vue": "Frontend",
        "angular": "Frontend",
        "backend": "Backend",
        "back end": "Backend",
        "api": "Backend",
        "server": "Backend",
        "node": "Backend",
        "python": "Backend",
        "java": "Backend",
        "golang": "Backend",
        "fullstack": "Fullstack",
        "full stack": "Fullstack",
        "mobile": "Mobile",
        "android": "Mobile",
        "ios": "Mobile",
        "data": "Data",
        "machine learning": "AI/ML",
        "ai": "AI/ML",
        "devops": "DevOps",
        "cloud": "DevOps",
        "qa": "QA",
        "test": "QA",
    }

    for hint in category_hints:
        lowered = hint.lower()
        for keyword, category in keyword_map.items():
            if keyword in lowered:
                return category
    return "General"


def build_candidate_interview_context(profile: dict) -> dict:
    academic_info = profile.get("academicInfo") or {}
    introduction = profile.get("introductionQuestions") or {}

    preferred_roles = _extract_preferred_roles(profile)
    technical_skills = _extract_candidate_skills(profile)
    soft_skills = _extract_soft_skills(profile)
    advantage_points = _extract_advantage_points(profile)
    level = _infer_candidate_level(profile)
    category = _infer_question_category(preferred_roles, technical_skills)

    summary_parts = [
        f"Preferred roles: {', '.join(preferred_roles)}" if preferred_roles else "",
        f"Category: {category}" if category else "",
        f"Level: {level}" if level else "",
        f"University: {academic_info.get('university', '')}",
        f"Major: {academic_info.get('major', '')}",
        (
            f"Graduation year: {academic_info.get('graduationYear')}"
            if academic_info.get("graduationYear")
            else ""
        ),
        f"GPA: {academic_info.get('gpa')}" if academic_info.get("gpa") else "",
        (
            f"Favorite technology: {introduction.get('favoriteTechnology', '')}"
            if introduction.get("favoriteTechnology")
            else ""
        ),
        (
            f"Why these roles: {introduction.get('whyTheseRoles', '')}"
            if introduction.get("whyTheseRoles")
            else ""
        ),
        (
            f"Future goals: {introduction.get('futureGoals', '')}"
            if introduction.get("futureGoals")
            else ""
        ),
        f"Technical skills: {', '.join(technical_skills[:12])}" if technical_skills else "",
        f"Soft skills: {', '.join(soft_skills[:8])}" if soft_skills else "",
        f"Strengths: {', '.join(advantage_points[:5])}" if advantage_points else "",
    ]

    return {
        "candidate_profile_id": str(profile.get("_id")),
        "user_id": str(profile.get("userId") or ""),
        "preferred_roles": preferred_roles,
        "category": category,
        "level": level,
        "technical_skills": technical_skills,
        "soft_skills": soft_skills,
        "summary": " | ".join(part for part in summary_parts if part),
    }


def generate_questions_for_candidate(
    user_id: str,
    round_name: str,
    n: int = 3,
) -> tuple[GeneratedQuestionSet, dict]:
    profile = get_candidate_profile(user_id)
    context = build_candidate_interview_context(profile)
    seeds = retrieve_seed_questions(
        category=context["category"],
        level=context["level"],
        skills=context["technical_skills"],
        k=max(6, n * 2),
    )
    if not seeds:
        raise ValueError("No seed questions found. Add more data or relax filters.")

    seed_payload = [
        {
            "id": str(doc["_id"]),
            "question": doc["question"],
            "suggestedAnswer": doc.get("suggestedAnswer", ""),
            "category": doc.get("category", ""),
            "level": doc.get("level", ""),
        }
        for doc in seeds
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You create ORIGINAL technical interview questions for an AI interview service.\n"
                "Use the seed questions only as inspiration.\n"
                "Do not copy or lightly paraphrase any seed question.\n"
                "Tailor the questions to the candidate profile, requested round, inferred level, and skills.\n"
                "Each question must include follow-ups and a scoring rubric.\n"
                "Return valid JSON only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "round": round_name,
                    "candidate_context": {
                        "preferred_roles": context["preferred_roles"],
                        "category": context["category"],
                        "level": context["level"],
                        "technical_skills": context["technical_skills"],
                        "soft_skills": context["soft_skills"],
                        "summary": context["summary"],
                    },
                    "n_questions": n,
                    "requirements": [
                        "Questions must be original",
                        "Use realistic interview framing",
                        "Avoid trivia-only questions",
                        "Include rubric and follow-ups",
                        "Match the candidate's experience level",
                    ],
                    "seed_questions": seed_payload,
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]

    resp = completion(
        model=GEN_MODEL,
        messages=messages,
        temperature=0.7,
        response_format=GeneratedQuestionSet,
    )

    content = resp.choices[0].message.content
    question_set = (
        GeneratedQuestionSet.model_validate_json(content)
        if isinstance(content, str)
        else GeneratedQuestionSet.model_validate(content)
    )

    request_meta = {
        "candidate_profile_id": context["candidate_profile_id"],
        "candidate_user_id": context["user_id"] or user_id,
        "round_name": round_name,
        "category": context["category"],
        "level": context["level"],
        "skills": context["technical_skills"],
        "seed_question_ids": [seed["id"] for seed in seed_payload],
    }
    return question_set, request_meta


def save_generated_set(question_set: GeneratedQuestionSet, request_meta: dict) -> None:
    for question in question_set.questions:
        if is_too_similar(question.question):
            continue

        doc = question.model_dump()
        doc["request_meta"] = request_meta
        doc["status"] = "draft"
        generated_questions.insert_one(doc)

# Follow-up question generation 
def get_follow_ups_for_candidate(
    user_id: str,
    last_question: str,
    last_response: str,
    end_round: bool = False,
) -> List[str]:
    profile = get_candidate_profile(user_id)
    context = build_candidate_interview_context(profile)

    messages = [
        {
            "role": "system",
            "content": (
                "You create ORIGINAL follow-up questions for an AI interview service.\n"
                "Tailor the questions to the candidate profile, previous question, and candidate's response.\n"
                "Each follow-up should be a natural next question an interviewer would ask.\n"
                "Return a list of follow-up questions in JSON format."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "candidate_context": {
                        "preferred_roles": context["preferred_roles"],
                        "category": context["category"],
                        "level": context["level"],
                        "technical_skills": context["technical_skills"],
                        "soft_skills": context["soft_skills"],
                        "summary": context["summary"],
                    },
                    "last_question": last_question,
                    "last_response": last_response,
                    "end_round": end_round,
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]

    resp = completion(
        model=GEN_MODEL,
        messages=messages,
        temperature=0.7,
        response_format=List[str],
    )

    content = resp.choices[0].message.content
    follow_ups = (
        [item.strip() for item in content]
        if isinstance(content, list)
        else []
    )
    return follow_ups

# Generate Starting Inteveriew Greeting
def generate_interview_greeting(user_id: str, round_name: str) -> str:
    profile = get_candidate_profile(user_id)
    context = build_candidate_interview_context(profile)

    messages = [
        {
            "role": "system",
            "content": (
                "You create a friendly and professional greeting message for the start of an AI interview.\n"
                "Tailor the greeting to the candidate profile and the interview round.\n"
                "The greeting should set a positive tone and provide a brief overview of what to expect in the interview.\n"
                "Return the greeting as a string."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "round": round_name,
                    "candidate_context": {
                        "preferred_roles": context["preferred_roles"],
                        "category": context["category"],
                        "level": context["level"],
                        "technical_skills": context["technical_skills"],
                        "soft_skills": context["soft_skills"],
                        "summary": context["summary"],
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]

    resp = completion(
        model=GEN_MODEL,
        messages=messages,
        temperature=0.7,
    )

    greeting = resp.choices[0].message.content.strip() if resp.choices else ""
    return greeting