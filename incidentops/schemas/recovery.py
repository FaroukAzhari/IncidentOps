from pydantic import BaseModel
from typing import Literal

RecoveryAction = Literal[
    "restart_auth_service", "restore_database_availability", "reset_application_state",
    "restore_database_configuration", "none",
]

ACTION_COMPONENTS = {
    "restart_auth_service": "auth", "restore_database_availability": "database",
    "reset_application_state": "api", "restore_database_configuration": "database",
}


class RecoveryResult(BaseModel):
    """Action outcome, not independent verification of incident resolution."""

    action: str
    succeeded: bool
    details: str
