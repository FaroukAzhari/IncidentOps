"""Allowlisted recovery tools for IncidentOps."""

from pathlib import Path

from environment.fault_state import set_fault
from incidentops.config import load_settings
from incidentops.schemas.recovery import RecoveryResult


def _clear_fault(
    fault_name: str,
    action_name: str,
    details: str,
    fault_database_path: Path | None = None,
) -> RecoveryResult:
    """Clear one specific allowlisted fault without affecting unrelated faults."""
    path = (
        fault_database_path
        if fault_database_path is not None
        else load_settings().fault_database_path
    )

    try:
        set_fault(fault_name, False, path=path)
    except Exception as exc:
        return RecoveryResult(
            action=action_name,
            succeeded=False,
            details=f"Recovery action failed: {type(exc).__name__}.",
        )

    return RecoveryResult(
        action=action_name,
        succeeded=True,
        details=details,
    )


def restore_database_availability(
    fault_database_path: Path | None = None,
) -> RecoveryResult:
    return _clear_fault(
        fault_name="database_down",
        action_name="restore_database_availability",
        details="Database availability fault cleared.",
        fault_database_path=fault_database_path,
    )


def restart_auth_service(
    fault_database_path: Path | None = None,
) -> RecoveryResult:
    return _clear_fault(
        fault_name="auth_down",
        action_name="restart_auth_service",
        details="Authentication service fault cleared.",
        fault_database_path=fault_database_path,
    )


def reset_application_state(
    fault_database_path: Path | None = None,
) -> RecoveryResult:
    return _clear_fault(
        fault_name="api_degraded",
        action_name="reset_application_state",
        details="Application degraded-state fault cleared.",
        fault_database_path=fault_database_path,
    )


def restore_database_configuration(
    fault_database_path: Path | None = None,
) -> RecoveryResult:
    return _clear_fault(
        fault_name="wrong_db_config",
        action_name="restore_database_configuration",
        details="Database configuration fault cleared.",
        fault_database_path=fault_database_path,
    )


RECOVERY_ACTIONS = {
    "restore_database_availability": restore_database_availability,
    "restart_auth_service": restart_auth_service,
    "reset_application_state": reset_application_state,
    "restore_database_configuration": restore_database_configuration,
}


def execute_recovery_action(
    action: str,
    fault_database_path: Path | None = None,
) -> RecoveryResult:
    """Execute only an explicitly allowlisted recovery action."""
    recovery_function = RECOVERY_ACTIONS.get(action)

    if recovery_function is None:
        return RecoveryResult(
            action=action,
            succeeded=False,
            details="Recovery action is not allowlisted.",
        )

    return recovery_function(fault_database_path=fault_database_path)