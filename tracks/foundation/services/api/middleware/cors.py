"""
CORS middleware configuration.
Restricts origins to overplanned.app + localhost:3000 (dev). No wildcards.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.api.config import settings


def setup_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        max_age=600,
    )
