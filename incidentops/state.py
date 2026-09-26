"""Shared state contract. Append reducers accept NEW entries only."""

from operator import add
from typing import Annotated

from pydantic import BaseModel, Field


class IncidentState(BaseModel):
    incident_id: str = Field(min_length=1)
    user_report: str = Field(min_length=1)
    service_status: dict[str, bool] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    monitoring_complete: bool = False
    observation_source: str | None = None
    requested_evidence: list[str] = Field(default_factory=list)
    evidence_attempts: int = Field(default=0, ge=0)
    max_evidence_attempts: int = Field(default=2, ge=0)
    suspected_root_cause: str | None = None
    diagnosis_confidence: float | None = Field(default=None, ge=0, le=1)
    diagnosis_evidence: list[str] = Field(default_factory=list)
    needs_more_evidence: bool | None = None
    recommended_action: str | None = None
    recovery_action: str | None = None
    recovery_attempts: int = Field(default=0, ge=0)
    max_recovery_attempts: int = Field(default=3, gt=0)
    recovery_result: str | None = None
    verification_passed: bool | None = None
    incident_resolved: bool = False
    errors: Annotated[list[str], add] = Field(default_factory=list)
    execution_history: Annotated[list[str], add] = Field(default_factory=list)
    final_status: str | None = None
