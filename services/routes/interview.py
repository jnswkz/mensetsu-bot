from typing import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from services.interview.candidate_pipeline import (
    generate_interview_greeting,
    generate_questions_for_candidate,
    get_follow_ups_for_candidate,
    save_generated_set,
)
from services.routes.common import generation_error_status, sse_data

router = APIRouter()


@router.get("/candidate_questions")
def get_candidate_questions(
    user_id: str,
    round_name: str = "technical_screen",
    n: int = 3,
    save: bool = False,
):
    try:
        question_set, request_meta = generate_questions_for_candidate(
            user_id=user_id,
            round_name=round_name,
            n=n,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=generation_error_status(exc),
            detail=str(exc),
        ) from exc

    if save:
        save_generated_set(question_set, request_meta)

    return {
        "request_meta": request_meta,
        "questions": question_set.model_dump()["questions"],
    }


@router.get("/candidate_questions_stream")
def stream_candidate_questions(
    user_id: str,
    round_name: str = "technical_screen",
    n: int = 3,
    save: bool = False,
):
    try:
        question_set, request_meta = generate_questions_for_candidate(
            user_id=user_id,
            round_name=round_name,
            n=n,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=generation_error_status(exc),
            detail=str(exc),
        ) from exc

    if save:
        save_generated_set(question_set, request_meta)

    def question_stream() -> Iterator[str]:
        yield sse_data(request_meta, event="meta")
        for index, question in enumerate(question_set.questions):
            yield sse_data(
                {"index": index, "question": question.model_dump()},
                event="question",
            )
        yield sse_data({}, event="done")

    return StreamingResponse(
        question_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/follow_up_questions")
def get_follow_up_questions(
    user_id: str,
    last_question: str,
    last_response: str,
    end_round: bool = False,
):
    try:
        follow_ups = get_follow_ups_for_candidate(
            user_id=user_id,
            last_question=last_question,
            last_response=last_response,
            end_round=end_round,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=generation_error_status(exc),
            detail=str(exc),
        ) from exc

    return {
        "follow_ups": follow_ups,
    }


@router.get("/follow_up_questions_stream")
def stream_follow_up_questions(
    user_id: str,
    last_question: str,
    last_response: str,
    end_round: bool = False,
):
    try:
        follow_ups = get_follow_ups_for_candidate(
            user_id=user_id,
            last_question=last_question,
            last_response=last_response,
            end_round=end_round,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=generation_error_status(exc),
            detail=str(exc),
        ) from exc

    def follow_up_stream() -> Iterator[str]:
        for index, follow_up in enumerate(follow_ups):
            yield sse_data({"index": index, "question": follow_up}, event="follow_up")
        yield sse_data({}, event="done")

    return StreamingResponse(
        follow_up_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/greeting")
def get_interview_greeting(user_id: str, round_name: str):
    try:
        greeting = generate_interview_greeting(user_id=user_id, round_name=round_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=generation_error_status(exc),
            detail=str(exc),
        ) from exc

    return {
        "greeting": greeting,
    }


@router.get("/greeting_stream")
def stream_interview_greeting(user_id: str, round_name: str):
    try:
        greeting = generate_interview_greeting(user_id=user_id, round_name=round_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=generation_error_status(exc),
            detail=str(exc),
        ) from exc

    def greeting_stream() -> Iterator[str]:
        yield sse_data({"greeting": greeting}, event="greeting")
        yield sse_data({}, event="done")

    return StreamingResponse(
        greeting_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
