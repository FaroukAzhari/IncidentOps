"""Observation specialist: collect a fixed baseline, never diagnose or recover."""

from collections.abc import Callable
from typing import Any

from incidentops.state import IncidentState
from incidentops.tools.monitoring_tools import (
    HealthResult, LogsResult, MetricsResult, MonitoringTools, ToolResult,
)


def make_monitoring_agent(tools: MonitoringTools) -> Callable[[IncidentState], dict[str, Any]]:
    """Inject the adapter once; future evidence selection belongs inside this node."""

    def monitor(state: IncidentState) -> dict[str, Any]:
        # Start fresh so a failed repeat cannot leave old observations looking current.
        statuses: dict[str, bool] = {}
        errors: list[str] = []

        def collect[T: ToolResult](
            name: str, call: Callable[[], T], schema: type[T]
        ) -> T | None:
            try:
                result = schema.model_validate(call())
            except Exception as exc:
                # Tool-boundary exceptions must not stop the other baseline checks.
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                return None
            if result.error is not None:
                errors.append(f"{name}: {result.error}")
                return None
            return result

        for service, call in (
            ("api", tools.check_api_health),
            ("auth", tools.check_auth_health),
            ("database", tools.check_database_health),
        ):
            result = collect(f"check_{service}_health", call, HealthResult)
            if result is not None:
                if result.service != service:
                    errors.append(f"check_{service}_health: unexpected service {result.service}")
                elif result.healthy is None:
                    errors.append(f"check_{service}_health: health unknown; {result.details}")
                else:
                    statuses[service] = result.healthy

        logs = collect("get_application_logs", tools.get_application_logs, LogsResult)
        metrics = collect("get_service_metrics", tools.get_service_metrics, MetricsResult)
        return {
            "service_status": statuses,
            "logs": logs.logs if logs is not None else [],
            "metrics": metrics.metrics if metrics is not None else {},
            "monitoring_complete": True,
            "observation_source": tools.observation_source,
            "errors": errors,
            "execution_history": [
                f"Monitoring Agent collected baseline observations for {state.incident_id} "
                f"(source={tools.observation_source}, collection_errors={len(errors)})."
            ],
        }

    return monitor
