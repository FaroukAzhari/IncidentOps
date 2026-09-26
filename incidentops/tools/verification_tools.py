"""Independent post-action checks; each method performs fresh I/O."""

from typing import Protocol

import httpx

from incidentops.config import Settings
from incidentops.schemas.verification import CheckResult
from incidentops.tools.functional_checks import check_login, check_profile
from incidentops.tools.local_monitoring_tools import LocalMonitoringTools


class VerificationTools(Protocol):
    def check_api_health(self) -> CheckResult: ...
    def check_auth_health(self) -> CheckResult: ...
    def check_database_health(self) -> CheckResult: ...
    def check_login(self) -> CheckResult: ...
    def check_profile(self) -> CheckResult: ...


class LocalVerificationTools:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self.health = LocalMonitoringTools(settings, transport)

    def _health(self, service: str) -> CheckResult:
        result = getattr(self.health, f"check_{service}_health")()
        return CheckResult(name=f"{service}_health", passed=result.healthy is True and result.error is None,
                           status_code=result.status_code, details=result.details, error=result.error)

    def check_api_health(self) -> CheckResult:
        return self._health("api")

    def check_auth_health(self) -> CheckResult:
        return self._health("auth")

    def check_database_health(self) -> CheckResult:
        return self._health("database")

    def check_login(self) -> CheckResult:
        return check_login(self.settings, self.transport)

    def check_profile(self) -> CheckResult:
        return check_profile(self.settings, self.transport)
