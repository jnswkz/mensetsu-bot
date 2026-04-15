from typing import List, Literal

from pydantic import BaseModel


class RubricPoint(BaseModel):
    signal: str
    weight: int


class GeneratedQuestion(BaseModel):
    question: str
    type: Literal["coding", "debugging", "system_design", "knowledge"]
    difficulty: Literal["easy", "medium", "hard"]
    skills: List[str]
    time_minutes: int
    follow_ups: List[str]
    rubric: List[RubricPoint]
    source_question_ids: List[str]


class GeneratedQuestionSet(BaseModel):
    questions: List[GeneratedQuestion]
