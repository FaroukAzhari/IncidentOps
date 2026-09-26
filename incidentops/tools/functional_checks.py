"""Read-only requests against the project's fixed demo identity."""

import httpx
from pydantic import BaseModel, ConfigDict

from incidentops.config import Settings
from incidentops.schemas.verification import CheckResult


class Identity(BaseModel):
    model_config = ConfigDict(strict=True)
    valid: bool
    username: str


class Profile(BaseModel):
    model_config = ConfigDict(strict=True)
    id: int
    username: str
    role: str


def check_login(settings: Settings, transport: httpx.BaseTransport | None = None) -> CheckResult:
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds, transport=transport, trust_env=False) as client:
            response = client.post(settings.auth_url.rstrip("/") + "/validate", json={"token": "demo-token"})
        if response.status_code != 200:
            return CheckResult(name="login", passed=False, status_code=response.status_code,
                               details="Authentication smoke test failed.")
        identity = Identity.model_validate(response.json())
        passed = identity.valid and identity.username == "demo"
        return CheckResult(name="login", passed=passed, status_code=200,
                           details="Demo login succeeded." if passed else "Unexpected login identity.")
    except Exception as exc:
        return CheckResult(name="login", passed=False, details="Login result unavailable.",
                           error=f"Login check failed ({type(exc).__name__}).")


def check_profile(settings: Settings, transport: httpx.BaseTransport | None = None) -> CheckResult:
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds, transport=transport, trust_env=False) as client:
            response = client.get(settings.api_url.rstrip("/") + "/profile",
                                  headers={"Authorization": "Bearer demo-token"})
        if response.status_code != 200:
            # Only publish known fixed application messages, never arbitrary response bodies.
            known = {
                "Application database configuration invalid", "Database connection unavailable",
                "Authentication service unavailable", "Authentication service unreachable",
                "Application running in degraded mode", "Database query failed",
            }
            try:
                detail = response.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            message = detail if isinstance(detail, str) and detail in known else "Profile smoke test failed."
            return CheckResult(name="profile", passed=False, status_code=response.status_code, details=message)
        profile = Profile.model_validate(response.json())
        passed = profile.id > 0 and profile.username == "demo" and profile.role == "student"
        return CheckResult(name="profile", passed=passed, status_code=200,
                           details="Authenticated database-backed profile succeeded." if passed else "Unexpected profile identity.")
    except Exception as exc:
        return CheckResult(name="profile", passed=False, details="Profile result unavailable.",
                           error=f"Profile check failed ({type(exc).__name__}).")
