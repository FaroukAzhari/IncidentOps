"""Shared API/CLI/evaluation entry point with explicit environment ownership."""

from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from incidentops.agents.recovery_agent import recover
from incidentops.config import Settings
from incidentops.demo import SCENARIOS, blocked_recovery, demo_diagnose, isolated_services
from incidentops.graph import build_graph
from incidentops.schemas.api import IncidentRequest, IncidentResponse, Step
from incidentops.state import IncidentState, add_counts
from incidentops.tools.local_monitoring_tools import LocalMonitoringTools


def apply_update(state: IncidentState, update: dict) -> IncidentState:
    """Apply the same reducers as LangGraph for an exact post-step UI snapshot.

    Checkpoint writes can lag behind a streamed node update, so reading the
    checkpointer at that instant can return the previous step's state.
    """
    values = state.model_dump()
    for key, value in update.items():
        if key in ("errors", "execution_history"):
            values[key] = values[key] + value
        elif key == "tool_calls":
            values[key] = add_counts(values[key], value)
        else:
            values[key] = value
    return IncidentState.model_validate(values)


def run_graph(graph, initial: IncidentState, thread_id: str, mode: str, scenario: str | None) -> IncidentResponse:
    # Graph steps are explicitly bounded; scale LangGraph's independent safety cap
    # above the maximum expected number of bounded cycles.
    config = {"configurable": {"thread_id": thread_id},
              "recursion_limit": 12 + 5 * (initial.max_retries + 1) + 2 * initial.max_evidence_attempts}
    started = last = perf_counter()
    steps = []
    current = initial
    try:
        for chunk in graph.stream(initial.model_dump(), config, stream_mode="updates"):
            for node, update in chunk.items():
                if node.startswith("__"):
                    continue
                now = perf_counter()
                current = apply_update(current, update)
                # JSON serialization is also the API boundary validation.
                step = Step(node=node, elapsed_ms=round((now - last) * 1000, 3), update=update, state=current)
                steps.append(Step.model_validate_json(step.model_dump_json()))
                last = now
        current = IncidentState.model_validate(graph.get_state(config).values)
    except Exception as exc:
        failure = {
            "final_status": "unresolved", "termination_reason": "workflow_error", "incident_resolved": False,
            "errors": [f"Workflow stopped ({type(exc).__name__})."],
            "execution_history": ["Workflow stopped safely before completion."],
        }
        current = apply_update(current, failure)
        try:
            # Preserve the same terminal outcome for checkpoint readers. This also
            # clears the failed task's pending retry when the saver is healthy.
            graph.update_state(config, failure, as_node="finalize")
            current = IncidentState.model_validate(graph.get_state(config).values)
        except Exception:
            # A broken checkpointer must not expose the original exception or
            # prevent the caller receiving the safe terminal result above.
            pass
    return IncidentResponse(thread_id=thread_id, mode=mode, scenario=scenario,
                            elapsed_ms=round((perf_counter() - started) * 1000, 3), state=current, steps=steps)


def run_incident(request: IncidentRequest, settings: Settings,
                 checkpointer: MemorySaver | None = None, *, diagnostic_node=None) -> IncidentResponse:
    thread_id = request.thread_id or str(uuid4())
    initial = IncidentState(incident_id=thread_id, user_report=request.report,
                            max_retries=settings.max_retries if request.max_retries is None else request.max_retries,
                            max_recovery_attempts=settings.max_recovery_attempts)
    if request.mode == "demo":
        with TemporaryDirectory(prefix="incidentops-demo-") as directory:
            with isolated_services(Path(directory), SCENARIOS[request.scenario][1]) as (local, monitor, verifier):
                recovery = partial(recover, executor=blocked_recovery) if request.scenario == "persistent_auth" else None
                graph = build_graph(monitor, checkpointer, settings=local, verification_tools=verifier,
                                    diagnostic_node=diagnostic_node or demo_diagnose, recovery_node=recovery)
                return run_graph(graph, initial, thread_id, "demo", request.scenario)
    graph = build_graph(LocalMonitoringTools(settings), checkpointer, settings=settings, diagnostic_node=diagnostic_node)
    return run_graph(graph, initial, thread_id, "gemini", None)
