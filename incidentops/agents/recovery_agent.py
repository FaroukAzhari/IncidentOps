"""Controlled Recovery Agent with allowlisted actions and attempt accounting."""

from typing import Any

from incidentops.state import IncidentState
from incidentops.tools.recovery_tools import RECOVERY_ACTIONS, execute_recovery_action


def recover(state: IncidentState) -> dict[str, Any]:
    """Execute a diagnosed recovery action when it is safe and allowed."""

    recommended_action = state.recommended_action

    # The Diagnostic Agent may explicitly decide that recovery is not justified.
    if recommended_action == "none":
        return {
            "execution_history": [
                "Recovery Agent skipped recovery because diagnosis did not justify an action."
            ],
        }

    # Recovery requires a recommendation from the Diagnostic Agent.
    if not recommended_action:
        return {
            "execution_history": [
                "Recovery Agent skipped recovery because no action was recommended."
            ],
        }

    # Never execute arbitrary LLM-generated actions.
    if recommended_action not in RECOVERY_ACTIONS:
        return {
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
            "recovery_result": "failed: maximum recovery attempts reached",
            "execution_history": [
                "Recovery Agent skipped recovery because the attempt limit was reached."
            ],
        }

    # A real allowlisted recovery action is attempted only after all checks pass.
    result = execute_recovery_action(recommended_action)

    new_attempt_count = state.recovery_attempts + 1

    outcome = "succeeded" if result.succeeded else "failed"

    return {
        "recovery_action": result.action,
        "recovery_attempts": new_attempt_count,
        "recovery_result": f"{outcome}: {result.details}",
        "execution_history": [
            (
                f"Recovery Agent attempted '{result.action}' "
                f"(attempt {new_attempt_count}/{state.max_recovery_attempts}) "
                f"and {outcome}."
            )
        ],
    }