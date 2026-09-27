"""Controlled Recovery Agent with allowlisted actions and attempt accounting."""

from typing import Any
from pathlib import Path
from collections.abc import Callable

from incidentops.state import IncidentState
from incidentops.progress import emit
from incidentops.tools.recovery_tools import RECOVERY_ACTIONS, execute_recovery_action
from incidentops.schemas.recovery import RecoveryResult


def recover(state: IncidentState, *, fault_database_path: Path | None = None,
            executor: Callable | None = None) -> dict[str, Any]:
    """Execute a diagnosed recovery action when it is safe and allowed."""

    # Do not present a previous attempt's result as the current outcome.
    cleared = {"recovery_action": None, "recovery_result": None}
    if state.observation_source != "local_services":
        return {
            **cleared,
            "execution_history": ["Recovery Agent skipped non-local observations; no action executed."],
        }

    if (state.needs_more_evidence is not False
            or not state.suspected_root_cause
            or state.diagnosis_confidence is None):
        return {
            **cleared,
            "execution_history": [
                "Recovery Agent skipped recovery: a current diagnosis with sufficient evidence is required."
            ],
        }

    recommended_action = state.recommended_action

    # The Diagnostic Agent may explicitly decide that recovery is not justified.
    if recommended_action == "none":
        return {
            **cleared,
            "execution_history": [
                "Recovery Agent skipped recovery because diagnosis did not justify an action."
            ],
        }

    # Recovery requires a recommendation from the Diagnostic Agent.
    if not recommended_action:
        return {
            **cleared,
            "execution_history": [
                "Recovery Agent skipped recovery because no action was recommended."
            ],
        }

    # Never execute arbitrary LLM-generated actions.
    if recommended_action not in RECOVERY_ACTIONS:
        return {
            **cleared,
            "recovery_result": (
                f"failed: recovery action '{recommended_action}' is not allowlisted"
            ),
            "execution_history": [
                "Recovery Agent rejected a non-allowlisted recovery action."
            ],
        }

    # Respect the configured recovery-attempt budget.
    if state.recovery_attempts >= state.max_recovery_attempts:
        return {
            **cleared,
            "recovery_result": "failed: maximum recovery attempts reached",
            "execution_history": [
                "Recovery Agent skipped recovery because the attempt limit was reached."
            ],
        }

    # A real allowlisted recovery action is attempted only after all checks pass.
    emit("tool_started", tool=recommended_action)
    try:
        result = RecoveryResult.model_validate((executor or execute_recovery_action)(
            recommended_action, fault_database_path=fault_database_path,
        ))
        if result.action != recommended_action:
            raise ValueError("Recovery returned a different action")
    except Exception as exc:
        result = RecoveryResult(action=recommended_action, succeeded=False,
                                details=f"Recovery failed ({type(exc).__name__}).")

    new_attempt_count = state.recovery_attempts + 1
    emit("tool_completed", tool=recommended_action, result=result.model_dump(mode="json"))

    outcome = "succeeded" if result.succeeded else "failed"

    return {
        "recovery_action": result.action,
        "recovery_attempts": new_attempt_count,
        "recovery_result": f"{outcome}: {result.details}",
        "tool_calls": {f"recover.{recommended_action}": 1},
        "execution_history": [
            (
                f"Recovery Agent attempted '{result.action}' "
                f"(attempt {new_attempt_count}/{state.max_recovery_attempts}) "
                f"and {outcome}."
            )
        ],
    }
