"""Shared state contract. Append reducers accept NEW entries only."""

from operator import add
from typing import Annotated

from pydantic import BaseModel, Field

from incidentops.schemas.verification import CheckResult, VerificationResult


def add_counts(previous: dict[str, int], current: dict[str, int]) -> dict[str, int]:
    return {key: previous.get(key, 0) + current.get(key, 0) for key in previous.keys() | current.keys()}


class IncidentState(BaseModel):
    incident_id: str = Field(min_length=1)
    user_report: str = Field(min_length=1)
    service_status: dict[str, bool] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    monitoring_complete: bool = False
    observation_source: str | None = None
    profile_check: CheckResult | None = None
    evidence_source: str = "monitoring"
    collection_errors: list[str] = Field(default_factory=list)
    requested_evidence: list[str] = Field(default_factory=list)
    evidence_attempts: int = Field(default=0, ge=0)
    max_evidence_attempts: int = Field(default=2, ge=0)
    suspected_root_cause: str | None = None
    suspected_component: str | None = None
    diagnosis_confidence: float | None = Field(default=None, ge=0, le=1)
    diagnosis_evidence: list[str] = Field(default_factory=list)
    needs_more_evidence: bool | None = None
    recommended_action: str | None = None
    recovery_action: str | None = None
    recovery_attempts: int = Field(default=0, ge=0)
    max_recovery_attempts: int = Field(default=3, gt=0)
    recovery_result: str | None = None
    verification_passed: bool | None = None
    verification_result: VerificationResult | None = None
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0, le=10)
    tool_calls: Annotated[dict[str, int], add_counts] = Field(default_factory=dict)
    incident_resolved: bool = False
    errors: Annotated[list[str], add] = Field(default_factory=list)
    execution_history: Annotated[list[str], add] = Field(default_factory=list)
    final_status: str | None = None
    termination_reason: str | None = None
