"""Observable checks, not an LLM judgment of whether a repair sounded successful."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckName = Literal["api_health", "auth_health", "database_health", "login", "profile"]


class CheckResult(BaseModel):
    model_config = ConfigDict(strict=True)
    name: CheckName
    passed: bool
    details: str
    status_code: int | None = Field(default=None, ge=100, le=599)
    error: str | None = None


class VerificationResult(BaseModel):
    verified: bool
    checks: list[CheckResult]
    summary: str
    remaining_problem: str | None = None
