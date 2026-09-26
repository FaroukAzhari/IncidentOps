from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from incidentops.schemas.recovery import ACTION_COMPONENTS, RecoveryAction


class Diagnosis(BaseModel):
    """Structured output produced by the Diagnostic Agent."""

    suspected_component: Literal["api", "auth", "database", "healthy", "unknown"]
    probable_cause: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    needs_more_evidence: bool
    requested_evidence: list[Literal[
        "api_health", "auth_health", "database_health", "application_logs", "service_metrics"
    ]] = Field(default_factory=list)
    recommended_action: RecoveryAction

    @model_validator(mode="after")
    def check_evidence_request(self) -> Self:
        if self.needs_more_evidence != bool(self.requested_evidence):
            raise ValueError("Evidence requests must match needs_more_evidence")
        if self.recommended_action != "none":
            if ACTION_COMPONENTS[self.recommended_action] != self.suspected_component:
                raise ValueError("Recovery action must match the diagnosed component")
            if not self.evidence:
                raise ValueError("Recovery recommendations require supporting evidence")
        return self
