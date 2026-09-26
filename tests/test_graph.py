from langgraph.checkpoint.memory import MemorySaver

from incidentops.graph import build_graph
from incidentops.state import IncidentState
from incidentops.tools.monitoring_tools import MockMonitoringTools


def test_graph_updates_checkpoints_and_honest_placeholders():
    saver = MemorySaver()
    graph = build_graph(checkpointer=saver)
    # Strict serializer mode may wrap the supplied saver. Verify persisted data
    # through that supplied saver below rather than relying on object identity.
    config = {"configurable": {"thread_id": "incident-001"}}
    initial = IncidentState(incident_id="a", user_report="Login failed")
    updates = list(graph.stream(initial.model_dump(), config, stream_mode="updates"))
    assert [next(iter(update)) for update in updates] == ["monitor", "diagnose", "recover", "verify", "finalize"]
    final = IncidentState.model_validate(graph.get_state(config).values)
    assert final.monitoring_complete and final.observation_source == "simulated"
    assert final.final_status == "monitoring_only" and not final.incident_resolved
    assert final.suspected_root_cause is final.verification_passed is final.recovery_result is None
    assert final.recovery_attempts == 0
    assert len(final.execution_history) == len(set(final.execution_history)) == 5
    saved = saver.get_tuple(config)
    assert saved is not None
    assert saved.checkpoint["channel_values"]["incident_id"] == initial.incident_id
    assert saved.checkpoint["channel_values"]["execution_history"] == final.execution_history
    history = list(graph.get_state_history(config))
    assert any(s.values.get("monitoring_complete") and s.values.get("final_status") is None for s in history)


def test_default_saver_and_thread_isolation():
    graph = build_graph()
    assert isinstance(graph.checkpointer, MemorySaver)
    for thread in ("one", "two"):
        result = graph.invoke(IncidentState(incident_id=thread, user_report=thread).model_dump(),
                              {"configurable": {"thread_id": thread}})
        assert result["incident_id"] == thread
    for thread in ("one", "two"):
        state = graph.get_state({"configurable": {"thread_id": thread}}).values
        assert state["user_report"] == thread and len(state["execution_history"]) == 5


def test_repeated_monitoring_replaces_snapshot_and_appends_only_new_errors(monkeypatch):
    tools = MockMonitoringTools()
    graph = build_graph(tools)
    config = {"configurable": {"thread_id": "repeat"}}
    graph.invoke(IncidentState(incident_id="a", user_report="r").model_dump(), config)
    def fail():
        raise TimeoutError("offline")
    monkeypatch.setattr(tools, "check_auth_health", fail)
    result = graph.invoke({"user_report": "collect again"}, config)
    assert "auth" not in result["service_status"]
    assert len(result["errors"]) == 1
    assert len(result["execution_history"]) == 10
