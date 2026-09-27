"""Four specialist nodes, bounded evidence requests, and verified retry routing."""

from collections.abc import Callable
from functools import partial
import logging
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from incidentops.agents.diagnostic_agent import diagnose
from incidentops.agents.monitoring_agent import make_monitoring_agent
from incidentops.agents.recovery_agent import recover
from incidentops.agents.verification_agent import verify
from incidentops.config import Settings
from incidentops.progress import EventSink, active_node, emit, sink
from incidentops.state import IncidentState
from incidentops.tools.monitoring_tools import MockMonitoringTools, MonitoringTools
from incidentops.tools.local_monitoring_tools import LocalMonitoringTools
from incidentops.tools.verification_tools import LocalVerificationTools, VerificationTools

logger = logging.getLogger(__name__)


def finalize(state: IncidentState) -> dict[str, Any]:
    """Only independent verification can mark a local incident resolved."""
    if state.observation_source == "simulated":
        status, reason = "monitoring_only", "offline_demo"
    elif state.verification_passed is True:
        status, reason = "resolved", "verification_passed"
    elif state.needs_more_evidence:
        status, reason = "unresolved", "evidence_exhausted"
    elif state.suspected_root_cause is None:
        status, reason = "unresolved", "diagnosis_failed"
    elif state.recovery_attempts >= state.max_recovery_attempts:
        status, reason = "unresolved", "recovery_limit"
    else:
        status, reason = "unresolved", "retries_exhausted"
    return {
        "final_status": status,
        "termination_reason": reason,
        "incident_resolved": status == "resolved",
        "execution_history": [f"Execution finished: {status} ({reason})."],
    }


def route_diagnosis(state: IncidentState) -> Literal["monitor", "recover"]:
    if (state.needs_more_evidence and state.requested_evidence
            and state.evidence_attempts < state.max_evidence_attempts):
        return "monitor"
    return "recover"


def route_verification(state: IncidentState) -> Literal["retry", "finalize"]:
    if (state.observation_source != "local_services" or state.verification_passed is True
            or state.suspected_root_cause is None or state.needs_more_evidence
            or state.recovery_attempts >= state.max_recovery_attempts
            or state.retry_count >= state.max_retries):
        return "finalize"
    return "retry"


def prepare_retry(state: IncidentState) -> dict[str, Any]:
    """Exactly one increment per retry; diagnosis consumes fresh verification evidence."""
    return {
        "retry_count": state.retry_count + 1, "incident_resolved": False,
        "execution_history": [f"Retry {state.retry_count + 1}/{state.max_retries}: return to Diagnostic Agent."],
    }


def observed(name: str, node: Callable, node_id: str, on_event: EventSink | None) -> Callable:
    def run(state: IncidentState) -> dict[str, Any]:
        logger.info("%s started (incident=%s)", name, state.incident_id)
        token = sink.set(on_event)
        node_token = active_node.set(node_id)
        try:
            emit("node_started", retry_count=state.retry_count,
                 recovery_attempts=state.recovery_attempts,
                 requested_evidence=state.requested_evidence)
            update = node(state)
        finally:
            active_node.reset(node_token)
            sink.reset(token)
        logger.info("%s completed (incident=%s)", name, state.incident_id)
        return update
    return run


def build_graph(
    tools: MonitoringTools | None = None,
    checkpointer: MemorySaver | None = None,
    *,
    settings: Settings | None = None,
    verification_tools: VerificationTools | None = None,
    diagnostic_node: Callable | None = None,
    recovery_node: Callable | None = None,
    on_event: EventSink | None = None,
) -> CompiledStateGraph:
    """Reuse the returned graph to inspect checkpoints within the same process."""
    settings = settings or getattr(tools, "settings", None)
    if verification_tools is None and isinstance(tools, LocalMonitoringTools):
        verification_tools = LocalVerificationTools(settings, tools.transport)
    diagnosis = diagnostic_node or (partial(diagnose, settings=settings) if settings else diagnose)
    recovery = recovery_node or (partial(recover, fault_database_path=settings.fault_database_path) if settings else recover)
    builder = StateGraph(IncidentState)
    builder.add_node("monitor", observed("Monitoring Agent", make_monitoring_agent(tools if tools is not None else MockMonitoringTools()), "monitor", on_event))
    builder.add_node("diagnose", observed("Diagnostic Agent", diagnosis, "diagnose", on_event))
    builder.add_node("recover", observed("Recovery Agent", recovery, "recover", on_event))
    builder.add_node("verify", observed("Verification Agent", partial(verify, tools=verification_tools), "verify", on_event))
    builder.add_node("retry", observed("Retry", prepare_retry, "retry", on_event))
    builder.add_node("finalize", observed("Finalize", finalize, "finalize", on_event))
    builder.add_edge(START, "monitor")
    builder.add_edge("monitor", "diagnose")
    builder.add_conditional_edges("diagnose", route_diagnosis)
    builder.add_edge("recover", "verify")
    builder.add_conditional_edges("verify", route_verification)
    builder.add_edge("retry", "diagnose")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer if checkpointer is not None else MemorySaver())
