from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class Diagnosis(BaseModel):
    """Structured output produced by the Diagnostic Agent."""

    suspected_component: str
    probable_cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    needs_more_evidence: bool
    requested_evidence: list[Literal[
        "api_health", "auth_health", "database_health", "application_logs", "service_metrics"
    ]] = Field(default_factory=list)
    recommended_action: str

    @model_validator(mode="after")
    def check_evidence_request(self) -> Self:
        if self.needs_more_evidence != bool(self.requested_evidence):
            raise ValueError("Evidence requests must match needs_more_evidence")
        return self
