from functools import partial

import pytest
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from environment.fault_state import get_fault_state
from incidentops.agents.recovery_agent import recover
from incidentops.config import Settings
from incidentops.demo import SCENARIOS, demo_diagnose, isolated_services, blocked_recovery
from incidentops.graph import build_graph, prepare_retry, route_verification
from incidentops.schemas.api import IncidentRequest
from incidentops.schemas.diagnosis import Diagnosis
from incidentops.state import IncidentState
from incidentops.workflow import apply_update, run_graph, run_incident


@pytest.mark.parametrize("count,route", [(0, "retry"), (1, "retry"), (2, "finalize")])
def test_retry_boundaries(count, route):
    state = IncidentState(incident_id="r", user_report="r", observation_source="local_services",
                          suspected_root_cause="auth unavailable", needs_more_evidence=False,
                          verification_passed=False, retry_count=count, max_retries=2)
    assert route_verification(state) == route
    if route == "retry":
        assert prepare_retry(state)["retry_count"] == count + 1
    assert route_verification(state.model_copy(update={"verification_passed": True})) == "finalize"
    assert route_verification(state.model_copy(update={"recovery_attempts": 3})) == "finalize"


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_full_supported_scenarios(scenario):
    result = run_incident(IncidentRequest(report="Investigate", scenario=scenario), Settings())
    assert not result.state.errors
    assert result.steps[0].state.monitoring_complete
    assert result.steps[0].state.profile_check is not None
    assert result.steps[-1].state == result.state
    assert result.state.incident_resolved == (scenario != "persistent_auth")
    assert result.state.final_status == ("unresolved" if scenario == "persistent_auth" else "resolved")
    expected_retries = 2 if scenario == "persistent_auth" else 1 if scenario == "multiple_faults" else 0
    assert result.state.retry_count == expected_retries
    assert result.state.tool_calls["verify.profile"] == 1 + expected_retries
    assert result.state.tool_calls["monitor.profile"] == 1
    assert result.state.tool_calls.get("diagnose.llm", 0) == 0
    if scenario == "healthy":
        assert result.state.recovery_attempts == 0
    if scenario == "multiple_faults":
        diagnoses = [s for s in result.steps if s.node == "diagnose"]
        assert [s.state.suspected_component for s in diagnoses] == ["auth", "database"]
        assert diagnoses[1].state.evidence_source == "verification"


@pytest.mark.parametrize("limit", [0, 1, 2, 4])
def test_skipped_recovery_still_has_finite_retry_budget(tmp_path, limit):
    def uncertain_action(state):
        update = demo_diagnose(state)
        update["recommended_action"] = "none"
        return update
    with isolated_services(tmp_path, ("auth_down",)) as (settings, monitor, verifier):
        graph = build_graph(monitor, settings=settings, verification_tools=verifier, diagnostic_node=uncertain_action)
        initial = IncidentState(incident_id="none", user_report="login failed", max_retries=limit)
        result = run_graph(graph, initial, "none", "demo", None)
        assert result.state.retry_count == limit and result.state.recovery_attempts == 0
        assert result.state.final_status == "unresolved" and result.state.termination_reason == "retries_exhausted"
        assert sum(step.node == "verify" for step in result.steps) == limit + 1


def test_recovery_limit_independent_of_retry_limit(tmp_path):
    with isolated_services(tmp_path, ("auth_down",)) as (settings, monitor, verifier):
        graph = build_graph(monitor, settings=settings, verification_tools=verifier,
                            diagnostic_node=demo_diagnose, recovery_node=partial(recover, executor=blocked_recovery))
        result = run_graph(graph, IncidentState(incident_id="x", user_report="x", max_recovery_attempts=1, max_retries=5), "x", "demo", None)
        assert result.state.recovery_attempts == 1 and result.state.retry_count == 0
        assert result.state.termination_reason == "recovery_limit"


def test_model_retry_receives_fresh_verification_not_stale_logs(tmp_path, diagnostic_model):
    def answer(messages):
        evidence = messages[1].content
        if "Latest evidence source: verification" in evidence:
            assert "'auth': True" in evidence and "'database': False" in evidence
            assert "Prior monitoring logs omitted" in evidence
            component, action = "database", "restore_database_availability"
        else:
            component, action = "auth", "restart_auth_service"
        return Diagnosis(suspected_component=component, probable_cause="Current failure", confidence=0.9,
                         evidence=["Current health failed"], needs_more_evidence=False, recommended_action=action)
    diagnostic_model.invoke.side_effect = answer
    with isolated_services(tmp_path, ("auth_down", "database_down")) as (settings, monitor, verifier):
        settings = settings.model_copy(update={"gemini_api_key": Settings(gemini_api_key="fake-key").gemini_api_key})
        graph = build_graph(monitor, settings=settings, verification_tools=verifier)
        result = run_graph(graph, IncidentState(incident_id="fresh", user_report="failure"), "fresh", "gemini", None)
        assert result.state.final_status == "resolved" and result.state.retry_count == 1
        assert result.state.tool_calls["diagnose.llm"] == 2
        assert not any(get_fault_state(settings.fault_database_path).model_dump().values())


def test_configuration_fault_detected_without_prior_requests(tmp_path):
    with isolated_services(tmp_path, ("wrong_db_config",)) as (settings, monitor, verifier):
        graph = build_graph(monitor, settings=settings, diagnostic_node=demo_diagnose)
        result = run_graph(graph, IncidentState(incident_id="config", user_report="failure"), "config", "demo", None)
        initial = result.steps[0].state
        assert all(initial.service_status.values()) and not initial.profile_check.passed
        assert initial.profile_check.details == "Application database configuration invalid"
        assert result.state.recovery_action == "restore_database_configuration" and result.state.incident_resolved


def test_missing_key_terminates_fault_without_recovery(tmp_path):
    with isolated_services(tmp_path, ("auth_down",)) as (settings, monitor, verifier):
        result = run_graph(build_graph(monitor, settings=settings),
                           IncidentState(incident_id="key", user_report="failure"), "key", "gemini", None)
        assert result.state.termination_reason == "diagnosis_failed"
        assert result.state.retry_count == result.state.recovery_attempts == 0
        assert get_fault_state(settings.fault_database_path).auth_down


@pytest.mark.parametrize("changes", [{"recommended_action": "shell"},
                                     {"recommended_action": "restore_database_availability"}, {"evidence": []}])
def test_diagnosis_cannot_recommend_unsupported_or_mismatched_action(changes):
    data = dict(suspected_component="auth", probable_cause="Failed", confidence=0.9, evidence=["auth down"],
                needs_more_evidence=False, recommended_action="restart_auth_service")
    data.update(changes)
    with pytest.raises(ValidationError):
        Diagnosis(**data)


def test_update_reducers_and_checkpoint_match_without_duplicates():
    initial = IncidentState(incident_id="reducers", user_report="test", errors=["old"], tool_calls={"x": 1})
    result = apply_update(initial, {"errors": ["new"], "tool_calls": {"x": 1, "y": 1}})
    assert result.errors == ["old", "new"] and result.tool_calls == {"x": 2, "y": 1}
    assert initial.errors == ["old"]
    saver = MemorySaver()
    graph = build_graph(checkpointer=saver)
    result = run_graph(graph, initial, "reducers", "demo", None)
    stored = IncidentState.model_validate(graph.get_state({"configurable": {"thread_id": "reducers"}}).values)
    assert stored == result.state == result.steps[-1].state
    assert len(result.state.execution_history) == 5


def test_unexpected_node_exception_returns_safe_failure(tmp_path):
    def fail(state):
        raise RuntimeError("private-key")
    with isolated_services(tmp_path) as (settings, monitor, verifier):
        graph = build_graph(monitor, settings=settings, diagnostic_node=fail)
        result = run_graph(graph, IncidentState(incident_id="bad", user_report="bad"), "bad", "demo", None)
        assert result.state.termination_reason == "workflow_error" and not result.state.incident_resolved
        assert "private-key" not in result.model_dump_json()
        checkpoint = graph.get_state({"configurable": {"thread_id": "bad"}})
        assert checkpoint.values["final_status"] == "unresolved" and not checkpoint.next
