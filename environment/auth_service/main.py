"""Local demo authentication service. The fixed demo token is not production auth."""

import logging
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from environment.fault_state import get_fault_state

logger = logging.getLogger(__name__)


class ValidationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)


class ValidationResponse(BaseModel):
    valid: bool
    username: str


def create_app(fault_path: Path | None = None) -> FastAPI:
    """An optional separate fault store keeps automated tests isolated."""
    application = FastAPI(title="IncidentOps Demo Authentication")

    def auth_unavailable() -> bool:
        try:
            return get_fault_state(fault_path).auth_down
        except (sqlite3.Error, OSError):
            logger.error("Authentication fault state unavailable")
            raise HTTPException(status_code=503, detail="Authentication fault state unavailable") from None

    @application.get("/health")
    def health() -> JSONResponse:
        unavailable = auth_unavailable()
        if unavailable:
            logger.error("Authentication service unavailable (injected fault)")
        return JSONResponse(
            status_code=503 if unavailable else 200,
            content={
                "service": "auth",
                "healthy": not unavailable,
                "status": "unavailable" if unavailable else "healthy",
            },
        )

    @application.post("/validate", response_model=ValidationResponse)
    def validate(request: ValidationRequest) -> ValidationResponse:
        if auth_unavailable():
            logger.error("Authentication validation unavailable (injected fault)")
            raise HTTPException(status_code=503, detail="Authentication service unavailable")
        if request.token != "demo-token":
            # Never include submitted tokens in diagnostic logs.
            logger.warning("Authentication rejected an invalid demo token")
            raise HTTPException(status_code=401, detail="Invalid demo token")
        return ValidationResponse(valid=True, username="demo")

    return application


app = create_app()
