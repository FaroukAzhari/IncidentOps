"""Real local observations through Student 1's unchanged monitoring interface."""

import sqlite3
from contextlib import closing

import httpx
from pydantic import BaseModel, ConfigDict

from environment.fault_state import get_fault_state
from incidentops.config import Settings
from incidentops.tools.monitoring_tools import HealthResult, LogsResult, MetricsResult


class HealthPayload(BaseModel):
    model_config = ConfigDict(strict=True)
    service: str
    healthy: bool
    status: str


class LocalMonitoringTools:
    observation_source = "local_services"

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _get(self, url: str) -> httpx.Response:
        with httpx.Client(timeout=self.settings.http_timeout_seconds,
                          transport=self.transport, trust_env=False) as client:
            return client.get(url)

    def _health(self, service: str, base_url: str) -> HealthResult:
        try:
            response = self._get(base_url.rstrip("/") + "/health")
            payload = HealthPayload.model_validate(response.json())
            if payload.service != service or response.status_code != (200 if payload.healthy else 503):
                raise ValueError("inconsistent health response")
            return HealthResult(service=service, healthy=payload.healthy,
                                status_code=response.status_code, details=payload.status)
        except Exception as exc:
            # Report collection failure as unknown, without URLs/credentials/body text.
            return HealthResult(service=service, healthy=None,
                                error=f"Health collection failed ({type(exc).__name__})")

    def check_api_health(self) -> HealthResult:
        return self._health("api", self.settings.api_url)

    def check_auth_health(self) -> HealthResult:
        return self._health("auth", self.settings.auth_url)

    def check_database_health(self) -> HealthResult:
        try:
            faults = get_fault_state(self.settings.fault_database_path)
        except Exception as exc:
            return HealthResult(service="database", healthy=None,
                                error=f"Database fault state unavailable ({type(exc).__name__})")
        if faults.database_down:
            return HealthResult(service="database", healthy=False, details="Injected database outage")
        try:
            # Check the real DB separately from the application's simulated config fault.
            uri = self.settings.database_path.resolve().as_uri() + "?mode=rw"
            with closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as connection:
                connection.execute("SELECT id FROM users LIMIT 1").fetchall()
            return HealthResult(service="database", healthy=True, details="SQLite users query succeeded")
        except (sqlite3.Error, OSError) as exc:
            return HealthResult(service="database", healthy=None,
                                error=f"Database probe failed ({type(exc).__name__})")

    def get_application_logs(self) -> LogsResult:
        try:
            response = self._get(self.settings.api_url.rstrip("/") + "/logs")
            response.raise_for_status()
            body = response.json()
            return LogsResult(logs=body["logs"])
        except Exception as exc:
            return LogsResult(error=f"Log collection failed ({type(exc).__name__})")

    def get_service_metrics(self) -> MetricsResult:
        try:
            response = self._get(self.settings.api_url.rstrip("/") + "/metrics")
            response.raise_for_status()
            body = response.json()
            return MetricsResult(metrics=body["metrics"])
        except Exception as exc:
            return MetricsResult(error=f"Metric collection failed ({type(exc).__name__})")
