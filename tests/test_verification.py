from unittest.mock import Mock

import httpx
import pytest

from incidentops.agents.verification_agent import verify
from incidentops.config import Settings
from incidentops.schemas.verification import CheckResult
from incidentops.state import IncidentState
from incidentops.tools.verification_tools import LocalVerificationTools

NAMES = ("api_health", "auth_health", "database_health", "login", "profile")


def state(**values):
    return IncidentState(incident_id="v", user_report="profile failed", observation_source="local_services", **values)


def passing_tools():
    tools = Mock()
    for name in NAMES:
        getattr(tools, f"check_{name}").return_value = CheckResult(name=name, passed=True, details="Current check passed")
    return tools


def test_verification_ignores_recovery_failure_and_uses_fresh_checks():
    tools = passing_tools()
    update = verify(state(recovery_result="failed: repair tool failed", service_status={"auth": False}), tools=tools)
    assert update["verification_passed"] and update["incident_resolved"]
    assert update["service_status"] == {"api": True, "auth": True, "database": True}
    for name in NAMES:
        getattr(tools, f"check_{name}").assert_called_once_with()
    assert len(update["verification_result"]["checks"]) == 5
    assert "recovery_attempts" not in update


@pytest.mark.parametrize("name", NAMES)
def test_any_failed_check_prevents_resolution_even_after_successful_recovery(name):
    tools = passing_tools()
    getattr(tools, f"check_{name}").return_value = CheckResult(name=name, passed=False, details="Still broken")
    update = verify(state(recovery_result="succeeded: fault cleared"), tools=tools)
    assert not update["verification_passed"] and not update["incident_resolved"]
    assert name in update["verification_result"]["remaining_problem"]
    for check in NAMES:
        getattr(tools, f"check_{check}").assert_called_once()


@pytest.mark.parametrize("bad", [None, {"name": "login", "passed": "true", "details": "bad"},
                                 CheckResult(name="profile", passed=True, details="Wrong identity")])
def test_malformed_check_is_unknown_and_does_not_stop_other_checks(bad):
    tools = passing_tools()
    tools.check_login.return_value = bad
    update = verify(state(), tools=tools)
    assert not update["verification_passed"] and update["errors"]
    tools.check_profile.assert_called_once()


def test_tool_exception_is_sanitized():
    tools = passing_tools()
    tools.check_auth_health.side_effect = RuntimeError("secret-key")
    update = verify(state(), tools=tools)
    assert "secret-key" not in str(update)
    assert "auth" not in update["service_status"]
    assert len(update["verification_result"]["checks"]) == 5


def test_simulated_run_cannot_verify_real_resolution():
    tools = passing_tools()
    initial = IncidentState(incident_id="s", user_report="demo", observation_source="simulated", verification_passed=True)
    update = verify(initial, tools=tools)
    assert update["verification_passed"] is None and not update["incident_resolved"]
    assert not tools.mock_calls


@pytest.mark.parametrize("body", [{"valid": "true", "username": "demo"}, {"valid": True, "username": "other"}, {}])
def test_login_smoke_test_validates_identity(body):
    tools = LocalVerificationTools(Settings(), httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    assert not tools.check_login().passed


@pytest.mark.parametrize("body", [{"id": "1", "username": "demo", "role": "student"},
                                  {"id": 1, "username": "other", "role": "student"}, {}])
def test_profile_smoke_test_validates_payload(body):
    tools = LocalVerificationTools(Settings(), httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    assert not tools.check_profile().passed


def test_functional_failures_never_publish_raw_response_or_exception():
    tools = LocalVerificationTools(Settings(), httpx.MockTransport(
        lambda request: httpx.Response(500, json={"detail": "private-token"})))
    assert "private-token" not in str(tools.check_profile())
    def fail(request):
        raise httpx.ConnectError("private-token", request=request)
    tools = LocalVerificationTools(Settings(), httpx.MockTransport(fail))
    assert not tools.check_login().passed and "private-token" not in str(tools.check_profile())
