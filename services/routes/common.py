import json
from typing import Any


def generation_error_status(exc: ValueError) -> int:
    return 404 if "candidate profile" in str(exc).lower() else 400


def sse_data(payload: Any, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
