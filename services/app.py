from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# from services.bot.response import get_response
from services.config import OAI_API_KEY
from services.interview.candidate_pipeline import generate_questions_for_candidate, save_generated_set, get_follow_ups_for_candidate, generate_interview_greeting
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"Hello": "World"}


# @app.get("/response")
# def get_bot_response(prompt: str):
#     response = get_response(OAI_API_KEY, prompt)
#     return {"response": response}


@app.get("/candidate_questions")
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
        status_code = 404 if "candidate profile" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if save:
        save_generated_set(question_set, request_meta)

    return {
        "request_meta": request_meta,
        "questions": question_set.model_dump()["questions"],
    }

@app.get("/candidate_questions_stream")
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
        status_code = 404 if "candidate profile" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    if save:
        save_generated_set(question_set, request_meta)

    def question_stream():
        for question in question_set.questions:
            yield f"data: {question.model_dump()}\n\n"

    return StreamingResponse(question_stream(), media_type="text/event-stream")

@app.get("/follow_up_questions")
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
        status_code = 404 if "candidate profile" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return {
        "follow_ups": follow_ups,
    }

@app.get("/follow_up_questions_stream")
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
        status_code = 404 if "candidate profile" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    def follow_up_stream():
        for follow_up in follow_ups:
            yield f"data: {follow_up.model_dump()}\n\n"

    return StreamingResponse(follow_up_stream(), media_type="text/event-stream")

@app.get("/greeting")
def get_interview_greeting(user_id: str, round_name: str):
    try:
        greeting = generate_interview_greeting(user_id=user_id, round_name=round_name)
    except ValueError as exc:
        status_code = 404 if "candidate profile" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return {
        "greeting": greeting,
    }

@app.get("/greeting_stream")
def stream_interview_greeting(user_id: str, round_name: str):
    try:
        greeting = generate_interview_greeting(user_id=user_id, round_name=round_name)
    except ValueError as exc:
        status_code = 404 if "candidate profile" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    def greeting_stream():
        yield f"data: {greeting}\n\n"

    return StreamingResponse(greeting_stream(), media_type="text/event-stream")
