import json
from typing import Any, Iterator, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field

from services.config import OAI_API_KEY
from services.interview.candidate_pipeline import (
    generate_questions_for_candidate,
    save_generated_set,
)
from services.routes.common import generation_error_status

router = APIRouter()

MAX_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_STREAMING_TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "coral"
SUPPORTED_TRANSCRIPTION_MODELS = {
    "whisper-1",
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "gpt-4o-mini-transcribe-2025-12-15",
    "gpt-4o-transcribe-diarize",
}
STREAMING_TRANSCRIPTION_MODELS = {
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "gpt-4o-mini-transcribe-2025-12-15",
}
TTS_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "application/octet-stream",
}


class TextToSpeechRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    model: str = DEFAULT_TTS_MODEL
    voice: str = DEFAULT_TTS_VOICE
    instructions: str | None = (
        "Speak clearly and professionally as an AI interviewer. "
        "Keep a warm, focused interview tone."
    )
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3"
    speed: float | None = Field(default=None, ge=0.25, le=4.0)


def get_openai_client() -> OpenAI:
    if not OAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OAI_API_KEY is not configured in the backend environment.",
        )
    return OpenAI(api_key=OAI_API_KEY)


async def read_audio_upload(file: UploadFile) -> tuple[str, bytes, str]:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio file is empty.")
    if len(audio_bytes) > MAX_AUDIO_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Audio file is too large. Uploads must be 25 MB or smaller.",
        )

    filename = file.filename or "audio.webm"
    content_type = file.content_type or "application/octet-stream"
    return filename, audio_bytes, content_type


def validate_transcription_model(model: str, stream: bool = False) -> None:
    if model not in SUPPORTED_TRANSCRIPTION_MODELS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported transcription model '{model}'. "
                f"Use one of: {', '.join(sorted(SUPPORTED_TRANSCRIPTION_MODELS))}."
            ),
        )
    if stream and model not in STREAMING_TRANSCRIPTION_MODELS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Streaming transcription is not supported for this model. "
                "Use gpt-4o-mini-transcribe or gpt-4o-transcribe for stream=True."
            ),
        )


def serialize_openai_event(event: Any) -> str:
    if hasattr(event, "model_dump_json"):
        return event.model_dump_json()
    if hasattr(event, "to_json"):
        return event.to_json()
    try:
        return json.dumps(event)
    except TypeError:
        return json.dumps({"event": str(event)})


def extract_transcript_text(transcription: Any) -> str:
    if isinstance(transcription, str):
        return transcription
    text = getattr(transcription, "text", "")
    if text:
        return text
    if isinstance(transcription, dict):
        return str(transcription.get("text", ""))
    return ""


def openai_error_response(exc: OpenAIError) -> HTTPException:
    return HTTPException(status_code=502, detail=f"OpenAI audio API error: {exc}")


def tts_headers(filename: str, text: str | None = None) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-cache",
        "Content-Disposition": f'inline; filename="{filename}"',
        "X-AI-Voice-Disclosure": "AI-generated voice",
    }
    if text:
        headers["X-Question-Text-Encoded"] = quote(text)
    return headers


def stream_tts_audio(
    text: str,
    model: str,
    voice: str,
    response_format: str,
    instructions: str | None = None,
    speed: float | None = None,
) -> Iterator[bytes]:
    params: dict[str, Any] = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": response_format,
    }
    if instructions:
        params["instructions"] = instructions
    if speed is not None:
        params["speed"] = speed

    try:
        response_context = get_openai_client().audio.speech.with_streaming_response.create(
            **params
        )
        response = response_context.__enter__()
    except OpenAIError as exc:
        raise openai_error_response(exc) from exc

    def chunks() -> Iterator[bytes]:
        try:
            for chunk in response.iter_bytes(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            response_context.__exit__(None, None, None)

    return chunks()


@router.post("/audio/transcriptions")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Query(DEFAULT_TRANSCRIPTION_MODEL),
    language: str | None = Query(None, description="Optional ISO-639-1 language code."),
    prompt: str | None = Query(None),
):
    validate_transcription_model(model)
    filename, audio_bytes, content_type = await read_audio_upload(file)

    params: dict[str, Any] = {
        "model": model,
        "file": (filename, audio_bytes, content_type),
    }
    if language:
        params["language"] = language
    if prompt and model != "gpt-4o-transcribe-diarize":
        params["prompt"] = prompt

    try:
        transcription = get_openai_client().audio.transcriptions.create(**params)
    except OpenAIError as exc:
        raise openai_error_response(exc) from exc

    return {
        "filename": filename,
        "model": model,
        "text": extract_transcript_text(transcription),
    }


@router.post("/audio/transcriptions/stream")
async def stream_transcribe_audio(
    file: UploadFile = File(...),
    model: str = Query(DEFAULT_STREAMING_TRANSCRIPTION_MODEL),
    language: str | None = Query(None, description="Optional ISO-639-1 language code."),
    prompt: str | None = Query(None),
):
    validate_transcription_model(model, stream=True)
    filename, audio_bytes, content_type = await read_audio_upload(file)
    client = get_openai_client()

    params: dict[str, Any] = {
        "model": model,
        "file": (filename, audio_bytes, content_type),
        "stream": True,
    }
    if language:
        params["language"] = language
    if prompt:
        params["prompt"] = prompt

    def events() -> Iterator[str]:
        try:
            stream = client.audio.transcriptions.create(**params)
            for event in stream:
                yield f"data: {serialize_openai_event(event)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except OpenAIError as exc:
            payload = json.dumps({"detail": f"OpenAI audio API error: {exc}"})
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/audio/speech")
@router.post("/text_to_speech")
def stream_text_to_speech(payload: TextToSpeechRequest):
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")

    return StreamingResponse(
        stream_tts_audio(
            text=text,
            model=payload.model,
            voice=payload.voice,
            response_format=payload.response_format,
            instructions=payload.instructions,
            speed=payload.speed,
        ),
        media_type=TTS_MEDIA_TYPES[payload.response_format],
        headers=tts_headers(f"speech.{payload.response_format}"),
    )


@router.get("/candidate_questions/speech")
def get_candidate_question_speech(
    user_id: str,
    round_name: str = "technical_screen",
    n: int = 3,
    save: bool = False,
    question_index: int = 0,
    model: str = DEFAULT_TTS_MODEL,
    voice: str = DEFAULT_TTS_VOICE,
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "mp3",
    speed: float | None = Query(default=None, ge=0.25, le=4.0),
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

    if question_index < 0 or question_index >= len(question_set.questions):
        raise HTTPException(
            status_code=400,
            detail=(
                f"question_index must be between 0 and "
                f"{len(question_set.questions) - 1}."
            ),
        )

    question_text = question_set.questions[question_index].question
    return StreamingResponse(
        stream_tts_audio(
            text=question_text,
            model=model,
            voice=voice,
            response_format=response_format,
            instructions=(
                "Speak as a friendly AI interviewer asking one concise interview "
                "question. Use a calm and professional tone."
            ),
            speed=speed,
        ),
        media_type=TTS_MEDIA_TYPES[response_format],
        headers=tts_headers(
            f"candidate-question-{question_index}.{response_format}",
            question_text,
        ),
    )
