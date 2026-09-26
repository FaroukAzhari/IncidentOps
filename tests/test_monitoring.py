import pytest

from incidentops.agents.monitoring_agent import make_monitoring_agent
from incidentops.state import IncidentState
from incidentops.tools.monitoring_tools import HealthResult, LogsResult, MetricsResult, MockMonitoringTools


def test_tool_contracts_and_partial_update():
    tools = MockMonitoringTools()
    for call in (tools.check_api_health, tools.check_auth_health, tools.check_database_health):
        assert isinstance(call(), HealthResult)
    assert isinstance(tools.get_application_logs(), LogsResult)
    assert isinstance(tools.get_service_metrics(), MetricsResult)
    state = IncidentState(incident_id="a", user_report="Login failed",
                          suspected_root_cause="existing diagnosis", recovery_attempts=1)
    before = state.model_dump()
    update = make_monitoring_agent(tools)(state)
    assert state.model_dump() == before
    assert update["service_status"] == {"api": True, "auth": False, "database": True}
    assert update["logs"] and update["metrics"]
    assert update["observation_source"] == "simulated"
    assert update["monitoring_complete"] is True
    assert update["errors"] == []
    assert set(update) == {"service_status", "logs", "metrics", "monitoring_complete",
                           "observation_source", "errors", "execution_history", "collection_errors",
                           "profile_check", "evidence_source", "verification_passed", "verification_result",
                           "incident_resolved", "final_status", "termination_reason", "tool_calls"}


@pytest.mark.parametrize("method,missing", [
    ("check_api_health", "api"), ("check_auth_health", "auth"),
    ("check_database_health", "database"), ("get_application_logs", "logs"),
    ("get_service_metrics", "metrics"),
])
def test_individual_failure_clears_stale_evidence(monkeypatch, method, missing):
    tools = MockMonitoringTools()
    def fail():
        raise TimeoutError("test timeout")
    monkeypatch.setattr(tools, method, fail)
    state = IncidentState(incident_id="a", user_report="report",
                          service_status={"api": True, "auth": True, "database": True},
                          logs=["stale"], metrics={"stale": 4.0}, errors=["previous"])
    update = make_monitoring_agent(tools)(state)
    assert update["monitoring_complete"]
    assert len(update["errors"]) == 1 and method in update["errors"][0]
    if missing in ("logs", "metrics"):
        assert not update[missing]
        assert len(update["service_status"]) == 3
    else:
        assert missing not in update["service_status"]
        assert len(update["service_status"]) == 2
        assert update["logs"] and update["metrics"]


@pytest.mark.parametrize("result", [
    HealthResult(service="auth", healthy=None),
    HealthResult(service="auth", healthy=True, error="collection failed"),
    HealthResult(service="api", healthy=True),
    {"service": "auth", "healthy": "invalid"},
])
def test_unknown_error_and_malformed_health(monkeypatch, result):
    tools = MockMonitoringTools()
    monkeypatch.setattr(tools, "check_auth_health", lambda: result)
    update = make_monitoring_agent(tools)(IncidentState(incident_id="a", user_report="r"))
    assert "auth" not in update["service_status"]
    assert len(update["errors"]) == 1
    assert update["logs"] and update["metrics"]
