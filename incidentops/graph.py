"""Finite Student 1 graph. Conditional recovery/evidence loops are future work."""

from typing import Any

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
    return {
        "final_status": "monitoring_only",
        "incident_resolved": False,
        "execution_history": ["Student 1 execution finished: monitoring only."],
    }


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
    # Student 3: replace this edge with bounded evidence-request routing.
    builder.add_edge("diagnose", "recover")
    builder.add_edge("recover", "verify")
    # Student 4: route pass to finalize, failed retries to diagnose, exhaustion to finalize.
    # Replace finalize's monitoring-only policy when implementing those real outcomes.
    builder.add_edge("verify", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else MemorySaver())
