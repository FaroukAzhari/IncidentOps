from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from incidentops.state import IncidentState

Scenario = Literal["healthy", "auth_down", "database_down", "api_degraded", "wrong_db_config", "multiple_faults", "persistent_auth"]


class IncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report: str = Field(min_length=1, max_length=4000)
    thread_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]{1,80}$")
    mode: Literal["demo", "gemini"] = "demo"
    scenario: Scenario = "auth_down"
    max_retries: int | None = Field(default=None, ge=0, le=10)

    @field_validator("report")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Incident report must not be blank")
        return value.strip()


class Step(BaseModel):
    node: str
    elapsed_ms: float
    update: dict
    state: IncidentState


class IncidentResponse(BaseModel):
    thread_id: str
    mode: Literal["demo", "gemini"]
    scenario: str | None
    elapsed_ms: float
    state: IncidentState
    steps: list[Step]
