"""Main demo API: independent API health and an auth/database-backed profile."""

import logging
import sqlite3
from collections import deque
from contextlib import asynccontextmanager
from time import perf_counter

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from environment.database import get_user
from environment.fault_state import FaultState, get_fault_state
from incidentops.config import Settings, load_settings

logger = logging.getLogger(__name__)


class AuthResult(BaseModel):
    model_config = ConfigDict(strict=True)
    valid: bool
    username: str = Field(min_length=1)


class Profile(BaseModel):
    id: int
    username: str
    role: str


def create_app(settings: Settings | None = None, transport: httpx.BaseTransport | None = None) -> FastAPI:
    recent_logs: deque[str] = deque(maxlen=100)
    metrics = {"api_response_ms": 0.0, "api_requests_total": 0.0, "api_errors_total": 0.0}

    class EvidenceHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            recent_logs.append(self.format(record))

    handler = EvidenceHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    @asynccontextmanager
    async def lifespan(application):
        logger.addHandler(handler)
        try:
            yield
        finally:
            logger.removeHandler(handler)

    application = FastAPI(title="IncidentOps Demo Application", lifespan=lifespan)

    @application.middleware("http")
    async def observe_requests(request, call_next):
        started = perf_counter()
        response = await call_next(request)
        if request.url.path in {"/health", "/profile"}:
            metrics["api_response_ms"] = (perf_counter() - started) * 1000.0
            metrics["api_requests_total"] += 1.0
            if response.status_code >= 500:
                metrics["api_errors_total"] += 1.0
            # Only fixed paths/statuses: no credentials, headers, or request bodies.
            recent_logs.append(f"HTTP {request.method} {request.url.path} {response.status_code}")
        return response

    @application.get("/logs")
    def logs() -> dict[str, list[str]]:
        return {"logs": list(recent_logs)}

    @application.get("/metrics")
    def service_metrics() -> dict[str, dict[str, float]]:
        return {"metrics": dict(metrics)}

    def current_context() -> tuple[Settings, FaultState]:
        config = settings if settings is not None else load_settings()
        try:
            return config, get_fault_state(config.fault_database_path)
        except (sqlite3.Error, OSError):
            logger.error("Application fault state unavailable")
            raise HTTPException(status_code=503, detail="Application fault state unavailable") from None

    @application.get("/health")
    def health() -> JSONResponse:
        # This reports the API itself. /profile exercises its dependencies.
        _, faults = current_context()
        if faults.api_degraded:
            logger.warning("Application running in degraded mode")
        return JSONResponse(
            status_code=503 if faults.api_degraded else 200,
            content={"service": "api", "healthy": not faults.api_degraded,
                     "status": "degraded" if faults.api_degraded else "healthy"},
        )

    @application.get("/profile", response_model=Profile)
    def profile(authorization: str | None = Header(default=None)) -> Profile:
        config, faults = current_context()
        if faults.api_degraded:
            logger.warning("Profile unavailable: application running in degraded mode")
            raise HTTPException(status_code=503, detail="Application running in degraded mode")
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise HTTPException(status_code=401, detail="Provide Authorization: Bearer demo-token")
        try:
            with httpx.Client(timeout=config.http_timeout_seconds, transport=transport,
                              trust_env=False) as client:
                response = client.post(config.auth_url.rstrip("/") + "/validate",
                                       json={"token": token.strip()})
        except httpx.RequestError:
            logger.error("Authentication service unreachable")
            raise HTTPException(status_code=503, detail="Authentication service unreachable") from None
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid demo token")
        if response.status_code != 200:
            logger.error("Authentication service unavailable")
            raise HTTPException(status_code=503, detail="Authentication service unavailable")
        try:
            identity = AuthResult.model_validate(response.json())
        except (ValueError, ValidationError):
            logger.error("Authentication service returned an invalid response")
            raise HTTPException(status_code=502, detail="Invalid authentication response") from None
        if not identity.valid:
            raise HTTPException(status_code=401, detail="Invalid demo token")
        if faults.database_down:
            logger.error("Database connection unavailable (injected fault)")
            raise HTTPException(status_code=500, detail="Database connection unavailable")
        if faults.wrong_db_config:
            # Model an application configuration failure without damaging the real DB.
            logger.error("Application database configuration invalid (injected fault)")
            raise HTTPException(status_code=500, detail="Application database configuration invalid")
        try:
            user = get_user(identity.username, config.database_path)
        except (sqlite3.Error, OSError):
            logger.error("Database query failed")
            raise HTTPException(status_code=500, detail="Database query failed") from None
        if user is None:
            raise HTTPException(status_code=404, detail="User profile not found")
        return Profile.model_validate(user)

    return application


app = create_app()
