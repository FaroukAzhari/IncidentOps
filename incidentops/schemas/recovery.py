from pydantic import BaseModel


class RecoveryResult(BaseModel):
    """Action outcome, not independent verification of incident resolution."""

    action: str
    succeeded: bool
    details: str
