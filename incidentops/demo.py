"""Explicit deterministic diagnosis double and isolated real-service demo fixtures.

This mode measures integration, not Gemini quality. It never reads a scenario
label or fault flags to diagnose; decisions use the collected shared evidence.
"""

from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from environment.app_service.main import create_app
from environment.auth_service.main import create_app as create_auth
from environment.database import initialize_database
from environment.fault_state import set_fault
from incidentops.config import Settings
from incidentops.schemas.diagnosis import Diagnosis
from incidentops.schemas.recovery import RecoveryResult
from incidentops.state import IncidentState
from incidentops.tools.local_monitoring_tools import LocalMonitoringTools
from incidentops.tools.verification_tools import LocalVerificationTools

SCENARIOS = {
    "healthy": ("Healthy system", ()),
    "auth_down": ("Authentication unavailable", ("auth_down",)),
    "database_down": ("Database unavailable", ("database_down",)),
    "api_degraded": ("API degraded", ("api_degraded",)),
    "wrong_db_config": ("Invalid database configuration", ("wrong_db_config",)),
    "multiple_faults": ("Authentication and database unavailable", ("auth_down", "database_down")),
    "persistent_auth": ("Authentication fault with deliberately blocked recovery", ("auth_down",)),
}


def demo_diagnose(state: IncidentState) -> dict:
    component, cause, action = "unknown", "Insufficient current evidence", "none"
    more = False
    if state.service_status.get("api") is False:
        component, cause, action = "api", "Application degraded", "reset_application_state"
    elif state.service_status.get("auth") is False:
        component, cause, action = "auth", "Authentication unavailable", "restart_auth_service"
    elif state.service_status.get("database") is False:
        component, cause, action = "database", "Database unavailable", "restore_database_availability"
    elif (state.profile_check and not state.profile_check.passed
          and state.profile_check.details == "Application database configuration invalid"):
        component, cause, action = "database", "Application database configuration invalid", "restore_database_configuration"
    elif (all(state.service_status.get(name) is True for name in ("api", "auth", "database"))
          and state.profile_check and state.profile_check.passed and not state.profile_check.error):
        component, cause = "healthy", "Current health and profile checks pass"
    else:
        more = True
    evidence = [f"Current health: {state.service_status}"]
    if state.profile_check:
        evidence.append(state.profile_check.details)
    result = Diagnosis(suspected_component=component, probable_cause=cause, confidence=0.0 if more else 1.0,
                       evidence=evidence, needs_more_evidence=more,
                       requested_evidence=["api_health", "auth_health", "database_health", "application_logs"] if more else [],
                       recommended_action=action)
    return {
        "suspected_component": result.suspected_component,
        "suspected_root_cause": f"{result.suspected_component}: {result.probable_cause}",
        "diagnosis_confidence": result.confidence, "diagnosis_evidence": result.evidence,
        "needs_more_evidence": result.needs_more_evidence, "requested_evidence": result.requested_evidence,
        "recommended_action": result.recommended_action,
        "tool_calls": {"diagnose.demo_rules": 1},
        "execution_history": [f"Diagnostic Agent (deterministic demo, no LLM): {cause}; action={action}."],
    }


def blocked_recovery(action: str, **kwargs) -> RecoveryResult:
    return RecoveryResult(action=action, succeeded=False, details="Recovery deliberately blocked for retry demonstration.")


@contextmanager
def isolated_services(directory: Path, faults: tuple[str, ...] = ()):
    settings = Settings(database_path=directory / "app.db", fault_database_path=directory / "faults.db")
    initialize_database(settings.database_path)
    for fault in faults:
        set_fault(fault, path=settings.fault_database_path)
    with TestClient(create_auth(settings.fault_database_path)) as auth:
        def auth_request(request):
            response = auth.request(request.method, request.url.path, content=request.content, headers=request.headers)
            return httpx.Response(response.status_code, json=response.json())
        with TestClient(create_app(settings, httpx.MockTransport(auth_request))) as api:
            def request(request):
                client = auth if request.url.port == 8002 else api
                response = client.request(request.method, request.url.path, content=request.content, headers=request.headers)
                return httpx.Response(response.status_code, json=response.json())
            transport = httpx.MockTransport(request)
            yield settings, LocalMonitoringTools(settings, transport), LocalVerificationTools(settings, transport)
