"""Observation specialist: collect evidence, never diagnose or recover."""

from collections.abc import Callable
from typing import Any

from incidentops.state import IncidentState
from incidentops.progress import emit
from incidentops.schemas.verification import CheckResult
from incidentops.tools.monitoring_tools import (
    HealthResult,
    LogsResult,
    MetricsResult,
    MonitoringTools,
    ToolResult,
)


def make_monitoring_agent(
    tools: MonitoringTools,
) -> Callable[[IncidentState], dict[str, Any]]:
    """Inject the monitoring adapter and collect current incident evidence."""

    def monitor(state: IncidentState) -> dict[str, Any]:
        # Start fresh so a failed repeat cannot leave old observations looking current.
        statuses: dict[str, bool] = {}
        errors: list[str] = []

        def collect[T: ToolResult](
            name: str,
            call: Callable[[], T],
            schema: type[T],
        ) -> T | None:
            emit("tool_started", tool=name)
            try:
                result = schema.model_validate(call())
            except Exception as exc:
                # Tool-boundary exceptions must not stop the other checks.
                errors.append(f"{name}: {type(exc).__name__}")
                emit("tool_completed", tool=name, result={"error": errors[-1]})
                return None

            emit("tool_completed", tool=name, result=result.model_dump(mode="json"))
            if result.error is not None:
                errors.append(f"{name}: {result.error}")
                return None

            return result

        # Collect current service health.
        for service, call in (
            ("api", tools.check_api_health),
            ("auth", tools.check_auth_health),
            ("database", tools.check_database_health),
        ):
            result = collect(
                f"check_{service}_health",
                call,
                HealthResult,
            )

            if result is not None:
                if result.service != service:
                    errors.append(
                        f"check_{service}_health: unexpected service {result.service}"
                    )
                elif result.healthy is None:
                    errors.append(
                        f"check_{service}_health: health unknown; {result.details}"
                    )
                else:
                    statuses[service] = result.healthy

        profile = None
        calls = {f"monitor.{name}": 1 for name in (
            "api_health", "auth_health", "database_health", "logs", "metrics"
        )}
        if hasattr(tools, "probe_profile"):
            emit("tool_started", tool="profile")
            calls["monitor.profile"] = 1
            try:
                profile = CheckResult.model_validate(tools.probe_profile())
                if profile.name != "profile":
                    raise ValueError("Unexpected check identity")
                if profile.error:
                    errors.append(profile.error)
            except Exception as exc:
                profile = None
                errors.append(f"Profile collection failed ({type(exc).__name__}).")
            emit("tool_completed", tool="profile", result=profile.model_dump(mode="json") if profile else {"error": errors[-1]})

        # Read logs after the functional probe to capture current failure evidence.
        logs = collect(
            "get_application_logs",
            tools.get_application_logs,
            LogsResult,
        )

        metrics = collect(
            "get_service_metrics",
            tools.get_service_metrics,
            MetricsResult,
        )

        update: dict[str, Any] = {
            "service_status": statuses,
            "logs": logs.logs if logs is not None else [],
            "metrics": metrics.metrics if metrics is not None else {},
            "monitoring_complete": True,
            "observation_source": tools.observation_source,
            "errors": errors,
            "collection_errors": errors,
            "profile_check": profile.model_dump() if profile else None,
            "evidence_source": "monitoring",
            "verification_passed": None,
            "verification_result": None,
            "incident_resolved": False,
            "final_status": None,
            "termination_reason": None,
            "tool_calls": calls,
        }

        # Only a monitoring pass explicitly requested by diagnosis counts as
        # an additional evidence attempt. The initial baseline does not.
        if state.requested_evidence:
            new_evidence_attempts = state.evidence_attempts + 1

            update["evidence_attempts"] = new_evidence_attempts
            update["execution_history"] = [
                (
                    "Monitoring Agent recollected evidence requested by the "
                    f"Diagnostic Agent for {state.incident_id} "
                    f"(attempt {new_evidence_attempts}/"
                    f"{state.max_evidence_attempts}, "
                    f"source={tools.observation_source}, "
                    f"collection_errors={len(errors)})."
                )
            ]
        else:
            update["execution_history"] = [
                (
                    f"Monitoring Agent collected baseline observations for "
                    f"{state.incident_id} "
                    f"(source={tools.observation_source}, "
                    f"collection_errors={len(errors)})."
                )
            ]

        return update

    return monitor
