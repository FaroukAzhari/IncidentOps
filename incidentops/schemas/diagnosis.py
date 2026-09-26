from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    """Structured output produced by the Diagnostic Agent."""

    suspected_component: str
    probable_cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    needs_more_evidence: bool
    requested_evidence: list[str] = Field(default_factory=list)
    recommended_action: str