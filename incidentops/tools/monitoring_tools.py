"""Stable synchronous adapter boundary; all bundled observations are simulated."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ToolResult(BaseModel):
    model_config = ConfigDict(strict=True)
    error: str | None = None


class HealthResult(ToolResult):
    service: Literal["api", "auth", "database"]
    healthy: bool | None
    status_code: int | None = Field(default=None, ge=100, le=599)
    details: str = ""


class LogsResult(ToolResult):
    logs: list[str] = Field(default_factory=list)


class MetricsResult(ToolResult):
    metrics: dict[str, float] = Field(default_factory=dict)


class MonitoringTools(Protocol):
    """Adapters must return validated results and enforce their own I/O timeouts."""

    observation_source: str

    def check_api_health(self) -> HealthResult: ...
    def check_auth_health(self) -> HealthResult: ...
    def check_database_health(self) -> HealthResult: ...
    def get_application_logs(self) -> LogsResult: ...
    def get_service_metrics(self) -> MetricsResult: ...


class MockMonitoringTools:
    """Fixed demonstration fixture, independent of report text or real services."""

    observation_source = "simulated"

    def check_api_health(self) -> HealthResult:
        return HealthResult(service="api", healthy=True, status_code=200,
                            details="Simulated API health response")

    def check_auth_health(self) -> HealthResult:
        return HealthResult(service="auth", healthy=False, status_code=503,
                            details="Simulated auth unavailable response")

    def check_database_health(self) -> HealthResult:
        return HealthResult(service="database", healthy=True,
                            details="Simulated database health check")

    def get_application_logs(self) -> LogsResult:
        return LogsResult(logs=["[SIMULATED] Authentication service unavailable"])

    def get_service_metrics(self) -> MetricsResult:
        return MetricsResult(metrics={"api_response_ms": 130.0})
