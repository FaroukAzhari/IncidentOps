"""Bounded diagnostic evidence routing; verification retries belong to Student 4."""

from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from incidentops.agents.diagnostic_agent import diagnose
from incidentops.agents.monitoring_agent import make_monitoring_agent
from incidentops.agents.recovery_agent import recover
from incidentops.agents.verification_agent import verify
from incidentops.state import IncidentState
from incidentops.tools.monitoring_tools import MockMonitoringTools, MonitoringTools


def finalize(state: IncidentState) -> dict[str, Any]:
    """Report the stage reached, without claiming the incident was resolved."""
    if state.observation_source == "simulated":
        status = "monitoring_only"
    elif state.needs_more_evidence:
        status = "evidence_exhausted"
    elif state.suspected_root_cause is None:
        status = "diagnosis_failed"
    elif state.recovery_action is not None:
        status = "awaiting_verification"
    else:
        status = "recovery_skipped"
    return {
        "final_status": status,
        "incident_resolved": False,
        "execution_history": [f"Execution finished: {status}; incident resolution is not verified."],
    }


def route_diagnosis(state: IncidentState) -> Literal["monitor", "recover"]:
    if (state.needs_more_evidence and state.requested_evidence
            and state.evidence_attempts < state.max_evidence_attempts):
        return "monitor"
    return "recover"


def build_graph(
    tools: MonitoringTools | None = None,
    checkpointer: MemorySaver | None = None,
) -> CompiledStateGraph:
    """Reuse the returned graph to inspect checkpoints within the same process."""
    builder = StateGraph(IncidentState)
    builder.add_node("monitor", make_monitoring_agent(tools if tools is not None else MockMonitoringTools()))
    builder.add_node("diagnose", diagnose)
    builder.add_node("recover", recover)
    builder.add_node("verify", verify)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "monitor")
    builder.add_edge("monitor", "diagnose")
    builder.add_conditional_edges("diagnose", route_diagnosis)
    builder.add_edge("recover", "verify")
    # Student 4: route pass to finalize, failed retries to diagnose, exhaustion to finalize.
    # Replace finalize's provisional statuses when implementing those real outcomes.
    builder.add_edge("verify", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else MemorySaver())
