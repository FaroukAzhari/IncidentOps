from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    """Student 2 will use this with ChatAnthropic.with_structured_output."""

    suspected_component: str
    probable_cause: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str]
    needs_more_evidence: bool
    recommended_action: str
