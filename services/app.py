from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.routes import audio, health, interview


def create_app() -> FastAPI:
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
    app.include_router(health.router)
    app.include_router(audio.router)
    app.include_router(interview.router)
    return app


app = create_app()
