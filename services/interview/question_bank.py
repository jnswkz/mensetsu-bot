from typing import List

from litellm import embedding
from pymongo.operations import SearchIndexModel

from services.config import EMBED_DIMS, EMBED_MODEL, QUESTION_BANK_VECTOR_INDEX
from services.db import question_bank


def ensure_vector_index() -> None:
    existing_names = {idx["name"] for idx in question_bank.list_search_indexes()}
    if QUESTION_BANK_VECTOR_INDEX in existing_names:
        return

    model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": EMBED_DIMS,
                    "similarity": "cosine",
                },
                {"type": "filter", "path": "category"},
                {"type": "filter", "path": "level"},
                {"type": "filter", "path": "isActive"},
                {"type": "filter", "path": "contributor.company"},
            ]
        },
        name=QUESTION_BANK_VECTOR_INDEX,
        type="vectorSearch",
    )
    question_bank.create_search_index(model=model)


def embed_texts(texts: List[str]) -> List[List[float]]:
    resp = embedding(model=EMBED_MODEL, input=texts)
    return [item["embedding"] for item in resp.data]


def upsert_source_question(doc: dict) -> None:
    """
    Expected source doc shape:
    {
      "category": "Frontend",
      "question": "HTML Semantic la gi?",
      "suggestedAnswer": "La viec dung the HTML co y nghia ro rang...",
      "level": "Intern",
      "contributor": {
        "name": "SEeds Admin",
        "company": "UIT"
      },
      "isActive": true
    }
    """
    if not doc.get("question"):
        raise ValueError("Source question must include a non-empty 'question'.")

    contributor = doc.get("contributor") or {}
    if not isinstance(contributor, dict):
        raise ValueError("'contributor' must be an object with optional 'name' and 'company'.")

    text_for_embedding = " | ".join(
        part
        for part in [
            doc["question"],
            doc.get("suggestedAnswer", ""),
            doc.get("category", ""),
            doc.get("level", ""),
            contributor.get("name", ""),
            contributor.get("company", ""),
        ]
        if part
    ).strip()

    enriched = dict(doc)
    enriched["contributor"] = {
        "name": contributor.get("name", ""),
        "company": contributor.get("company", ""),
    }
    enriched["isActive"] = doc.get("isActive", True)
    enriched["embedding"] = embed_texts([text_for_embedding])[0]

    question_bank.update_one(
        {
            "question": doc["question"],
            "category": enriched.get("category"),
            "level": enriched.get("level"),
        },
        {"$set": enriched},
        upsert=True,
    )


def retrieve_seed_questions(
    category: str,
    level: str,
    skills: List[str],
    k: int = 6,
) -> List[dict]:
    ensure_vector_index()

    query_text = (
        f"{level} {category} interview questions "
        f"covering {', '.join(skills) if skills else 'core fundamentals'}"
    )
    query_vector = embed_texts([query_text])[0]

    filters = [
        {"$and": [{"isActive": True}, {"category": category}, {"level": level}]},
        {"$and": [{"isActive": True}, {"category": category}]},
        {"isActive": True},
    ]

    for filter_doc in filters:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": QUESTION_BANK_VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(100, k * 20),
                    "limit": k,
                    "filter": filter_doc,
                }
            },
            {
                "$project": {
                    "question": 1,
                    "suggestedAnswer": 1,
                    "category": 1,
                    "level": 1,
                    "contributor": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        results = list(question_bank.aggregate(pipeline))
        if results:
            return results

    return []


def is_too_similar(question_text: str, threshold: float = 0.93) -> bool:
    query_vector = embed_texts([question_text])[0]

    pipeline = [
        {
            "$vectorSearch": {
                "index": QUESTION_BANK_VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 50,
                "limit": 1,
            }
        },
        {"$project": {"score": {"$meta": "vectorSearchScore"}}},
    ]

    top = next(iter(question_bank.aggregate(pipeline)), None)
    return bool(top and top["score"] >= threshold)
