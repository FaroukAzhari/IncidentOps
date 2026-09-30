from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from langchain_core.exceptions import OutputParserException

from environment.app_service.main import create_app
from environment.auth_service.main import create_app as create_auth
from environment.database import initialize_database
from environment.fault_state import FAULT_NAMES, get_fault_state, set_fault
from incidentops.agents import diagnostic_agent, recovery_agent
from incidentops.config import Settings
from incidentops.graph import build_graph
from incidentops.schemas.diagnosis import Diagnosis
from incidentops.state import IncidentState
from incidentops.tools.monitoring_tools import MockMonitoringTools
from incidentops.tools.local_monitoring_tools import LocalMonitoringTools
from incidentops.tools import recovery_tools
from incidentops.tools.recovery_tools import execute_recovery_action


def diagnosis(needs_more=False, action="restart_auth_service"):
    components = {"restore_database_availability": "database", "restore_database_configuration": "database",
                  "reset_application_state": "api"}
    return Diagnosis(
        suspected_component=components.get(action, "auth"), probable_cause="Authentication unavailable",
        confidence=0.8, evidence=["Current auth health is false"],
        needs_more_evidence=needs_more,
        requested_evidence=["auth_health"] if needs_more else [],
        recommended_action=action,
    )


def state(**changes):
    return IncidentState(**{
        "incident_id": "student3-test", "user_report": "Users cannot log in",
        "observation_source": "local_services", "monitoring_complete": True,
        "service_status": {"api": True, "auth": False, "database": True},
        "max_retries": 0,
        **changes,
    })


class LocalEvidenceFixture(MockMonitoringTools):
    """Fixed evidence for testing graph control flow, not an HTTP adapter."""
    observation_source = "local_services"


def test_structured_diagnosis_uses_evidence_and_configured_model(diagnostic_model):
    diagnostic_model.invoke.return_value = diagnosis()
    initial = state(logs=["auth unavailable"], metrics={"api_response_ms": 12.0})
    update = diagnostic_agent.diagnose(initial)
    diagnostic_agent.ChatGoogleGenerativeAI.assert_called_once_with(
        model="gemini-3.5-flash-lite", google_api_key="offline-test-key", timeout=30.0, max_retries=0,
    )
    diagnostic_model.with_structured_output.assert_called_once_with(Diagnosis, method="json_schema")
    prompt = diagnostic_model.invoke.call_args.args[0][1].content
    for value in (initial.user_report, str(initial.service_status), str(initial.logs), str(initial.metrics)):
        assert value in prompt
    assert update["suspected_root_cause"] == "auth: Authentication unavailable"
    assert update["diagnosis_confidence"] == 0.8
    assert update["diagnosis_evidence"] == diagnosis().evidence
    assert update["recommended_action"] == "restart_auth_service"
    assert initial.suspected_root_cause is None
    assert "recovery_action" not in update


@pytest.mark.parametrize("failure", ["missing_key", "construction", "invoke", "invalid_output"])
def test_diagnosis_failure_clears_stale_action(diagnostic_model, monkeypatch, failure):
    if failure == "missing_key":
        monkeypatch.setattr(diagnostic_agent, "load_settings", lambda: Settings(gemini_api_key=""))
    elif failure == "construction":
        diagnostic_agent.ChatGoogleGenerativeAI.side_effect = RuntimeError("secret credential")
    elif failure == "invoke":
        diagnostic_model.invoke.side_effect = RuntimeError("secret credential")
    else:
        diagnostic_model.invoke.return_value = None
    update = diagnostic_agent.diagnose(state(
        suspected_root_cause="old cause", diagnosis_confidence=0.9,
        diagnosis_evidence=["old evidence"], needs_more_evidence=False,
        requested_evidence=["auth_health"], recommended_action="restart_auth_service",
    ))
    assert update["recommended_action"] is update["suspected_root_cause"] is None
    assert update["diagnosis_confidence"] is update["needs_more_evidence"] is None
    assert update["requested_evidence"] == update["diagnosis_evidence"] == []
    assert len(update["errors"]) == len(update["execution_history"]) == 1
    assert "secret credential" not in str(update)


@pytest.mark.parametrize("evidence_request,needed", [([], True), (["shell_command"], True), (["auth_health"], False)])
def test_invalid_evidence_requests_are_rejected(evidence_request, needed):
    data = diagnosis().model_dump()
    data.update(requested_evidence=evidence_request, needs_more_evidence=needed)
    with pytest.raises(ValidationError):
        Diagnosis.model_validate(data)


def test_parser_failure_retries_once_then_accepts_valid_model_decision(diagnostic_model):
    diagnostic_model.invoke.side_effect = [OutputParserException("untrusted output"),
                                          diagnosis(action="reset_application_state")]
    update = diagnostic_agent.diagnose(state())
    assert update["recommended_action"] == "reset_application_state"
    assert update["tool_calls"]["diagnose.llm"] == 2
    assert "errors" not in update
    assert "untrusted output" not in str(diagnostic_model.invoke.call_args)


def test_repeated_parser_failure_is_bounded_and_cannot_authorize_repair(diagnostic_model):
    diagnostic_model.invoke.side_effect = OutputParserException("private raw output")
    update = diagnostic_agent.diagnose(state(recommended_action="reset_application_state"))
    assert diagnostic_model.invoke.call_count == 2
    assert update["recommended_action"] is None
    assert update["tool_calls"]["diagnose.llm"] == 2
    assert "after two attempts" in update["errors"][0]
    assert "private raw output" not in str(update)


@pytest.mark.parametrize("budget", [0, 1, 2])
def test_evidence_loop_is_bounded_and_does_not_recover(diagnostic_model, student3_settings, budget, failed_verification):
    diagnostic_model.invoke.return_value = diagnosis(needs_more=True)
    set_fault("auth_down", path=student3_settings.fault_database_path)
    graph = build_graph(LocalEvidenceFixture(), verification_tools=failed_verification)
    config = {"configurable": {"thread_id": "bounded"}}
    updates = list(graph.stream(state(max_evidence_attempts=budget).model_dump(), config, stream_mode="updates"))
    nodes = [next(iter(update)) for update in updates]
    result = graph.get_state(config).values
    assert nodes.count("monitor") == nodes.count("diagnose") == budget + 1
    assert result["evidence_attempts"] == budget
    assert result["recovery_attempts"] == 0
    assert result["final_status"] == "unresolved" and result["termination_reason"] == "evidence_exhausted"
    assert not result["incident_resolved"]
    assert get_fault_state(student3_settings.fault_database_path).auth_down


def test_additional_evidence_then_recovery(diagnostic_model, student3_settings, failed_verification):
    diagnostic_model.invoke.side_effect = [diagnosis(needs_more=True), diagnosis()]
    set_fault("auth_down", path=student3_settings.fault_database_path)
    set_fault("database_down", path=student3_settings.fault_database_path)
    result = build_graph(LocalEvidenceFixture(), verification_tools=failed_verification).invoke(
        state().model_dump(), {"configurable": {"thread_id": "recover"}},
    )
    assert result["evidence_attempts"] == result["recovery_attempts"] == 1
    assert result["requested_evidence"] == []
    assert result["recovery_action"] == "restart_auth_service"
    assert result["recovery_result"].startswith("succeeded:")
    assert result["final_status"] == "unresolved"
    assert result["verification_passed"] is False and not result["incident_resolved"]
    faults = get_fault_state(student3_settings.fault_database_path)
    assert not faults.auth_down and faults.database_down


@pytest.mark.parametrize("failure", ["missing_key", "invoke"])
def test_checkpoint_replay_cannot_reuse_failed_diagnosis(diagnostic_model, student3_settings, monkeypatch, failure, failed_verification):
    diagnostic_model.invoke.return_value = diagnosis()
    graph = build_graph(LocalEvidenceFixture(), verification_tools=failed_verification)
    config = {"configurable": {"thread_id": "replay"}}
    graph.invoke(state().model_dump(), config)
    set_fault("auth_down", path=student3_settings.fault_database_path)
    if failure == "missing_key":
        monkeypatch.setattr(diagnostic_agent, "load_settings", lambda: Settings(gemini_api_key=""))
    else:
        diagnostic_model.invoke.side_effect = RuntimeError("offline")
    result = graph.invoke({"user_report": "Check again"}, config)
    assert result["recovery_attempts"] == 1
    assert result["recommended_action"] is result["recovery_action"] is result["recovery_result"] is None
    assert result["final_status"] == "unresolved" and result["termination_reason"] == "diagnosis_failed"
    assert get_fault_state(student3_settings.fault_database_path).auth_down


def test_mock_graph_stays_offline_and_preserves_real_faults(diagnostic_model, student3_settings):
    set_fault("auth_down", path=student3_settings.fault_database_path)
    result = build_graph().invoke(state().model_dump(), {"configurable": {"thread_id": "mock"}})
    diagnostic_agent.ChatGoogleGenerativeAI.assert_not_called()
    assert result["final_status"] == "monitoring_only"
    assert result["errors"] == [] and result["recovery_attempts"] == 0
    assert get_fault_state(student3_settings.fault_database_path).auth_down


@pytest.mark.parametrize("changes", [
    {"observation_source": "simulated"}, {"observation_source": None},
    {"needs_more_evidence": True}, {"needs_more_evidence": None},
    {"suspected_root_cause": None}, {"recommended_action": "none"},
    {"recommended_action": None}, {"recommended_action": "arbitrary_command"},
    {"recovery_attempts": 3},
])
def test_recovery_guards_never_execute_tools(monkeypatch, changes):
    execute = Mock()
    monkeypatch.setattr(recovery_agent, "execute_recovery_action", execute)
    values = dict(suspected_root_cause="auth unavailable", diagnosis_confidence=0.8,
                  needs_more_evidence=False, recommended_action="restart_auth_service",
                  recovery_action="old", recovery_result="succeeded: old")
    values.update(changes)
    update = recovery_agent.recover(state(**values))
    execute.assert_not_called()
    assert "recovery_attempts" not in update and update["recovery_action"] is None
    assert update["recovery_result"] != "succeeded: old"


@pytest.mark.parametrize("action,fault", [
    ("restart_auth_service", "auth_down"), ("restore_database_availability", "database_down"),
    ("reset_application_state", "api_degraded"), ("restore_database_configuration", "wrong_db_config"),
])
def test_targeted_recovery_preserves_unrelated_faults(student3_settings, action, fault):
    path = student3_settings.fault_database_path
    for name in FAULT_NAMES:
        set_fault(name, path=path)
    update = recovery_agent.recover(state(
        suspected_root_cause="current failure", diagnosis_confidence=0.8,
        needs_more_evidence=False, recommended_action=action,
    ))
    flags = get_fault_state(path).model_dump()
    assert not flags[fault] and all(flags[name] for name in FAULT_NAMES if name != fault)
    assert update["recovery_attempts"] == 1 and update["recovery_action"] == action
    assert update["recovery_result"].startswith("succeeded:")
    assert "incident_resolved" not in update and "verification_passed" not in update


def test_failed_recovery_counts_attempt_and_sanitizes_error(student3_settings, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError(f"private path: {student3_settings.fault_database_path}")
    monkeypatch.setattr(recovery_tools, "set_fault", fail)
    update = recovery_agent.recover(state(
        suspected_root_cause="auth unavailable", diagnosis_confidence=0.8,
        needs_more_evidence=False, recommended_action="restart_auth_service",
    ))
    assert update["recovery_attempts"] == 1
    assert update["recovery_result"].startswith("failed:")
    assert str(student3_settings.fault_database_path.parent) not in update["recovery_result"]


def test_unknown_tool_action_cannot_create_storage(tmp_path):
    path = tmp_path / "absent.db"
    result = execute_recovery_action("arbitrary_command", path)
    assert not result.succeeded and not path.exists()


@pytest.mark.parametrize("fault,action,component,status_code", [
    ("auth_down", "restart_auth_service", "auth", 503),
    ("database_down", "restore_database_availability", "database", 500),
    ("api_degraded", "reset_application_state", "api", 503),
    ("wrong_db_config", "restore_database_configuration", "database", 500),
])
def test_local_service_monitoring_to_recovery(
    student3_settings, diagnostic_model, fault, action, component, status_code,
):
    settings = student3_settings
    initialize_database(settings.database_path)
    set_fault(fault, path=settings.fault_database_path)
    diagnostic_model.invoke.return_value = diagnosis(action=action).model_copy(
        update={"suspected_component": component},
    )
    with TestClient(create_auth(settings.fault_database_path)) as auth:
        def auth_request(request):
            response = auth.post("/validate", content=request.content,
                                 headers={"Content-Type": "application/json"})
            return httpx.Response(response.status_code, json=response.json())
        with TestClient(create_app(settings, httpx.MockTransport(auth_request))) as api:
            headers = {"Authorization": "Bearer demo-token"}
            assert api.get("/profile", headers=headers).status_code == status_code
            def request(request):
                client = auth if request.url.port == 8002 else api
                response = client.request(request.method, request.url.path, content=request.content, headers=request.headers)
                return httpx.Response(response.status_code, json=response.json())
            tools = LocalMonitoringTools(settings, httpx.MockTransport(request))
            result = build_graph(tools).invoke(
                state().model_dump(), {"configurable": {"thread_id": fault}},
            )
            assert not result["errors"]
            assert result["recovery_action"] == action and result["recovery_attempts"] == 1
            assert result["recovery_result"].startswith("succeeded:")
            assert result["final_status"] == "resolved"
            assert result["incident_resolved"] and result["verification_passed"] is True
            prompt = diagnostic_model.invoke.call_args.args[0][1].content
            assert "Current service health:" in prompt and str(result["logs"]) in prompt
            assert not any(get_fault_state(settings.fault_database_path).model_dump().values())
            # An independent assertion, not an implementation of Student 4's agent.
            assert api.get("/profile", headers=headers).status_code == 200
            assert all(call().healthy for call in (
                tools.check_api_health, tools.check_auth_health, tools.check_database_health,
            ))
