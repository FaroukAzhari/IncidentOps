"""Measure known outcomes. Default uses demo diagnosis; --live measures Gemini too."""

import argparse
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from environment.fault_state import get_fault_state
from incidentops.agents.recovery_agent import recover
from incidentops.config import Settings, load_settings
from incidentops.demo import SCENARIOS, blocked_recovery, demo_diagnose, isolated_services
from incidentops.graph import build_graph
from incidentops.state import IncidentState
from incidentops.workflow import run_graph

DATASET = Path(__file__).with_name("incidents.json")


def evaluate(live: bool = False, settings: Settings | None = None) -> dict:
    settings = settings or load_settings()
    if live and not settings.gemini_api_key.get_secret_value():
        raise ValueError("Live evaluation requires GEMINI_API_KEY and model access.")
    rows = []
    for case in json.loads(DATASET.read_text(encoding="utf-8")):
        with TemporaryDirectory(prefix="incidentops-eval-") as directory:
            with isolated_services(Path(directory), SCENARIOS[case["id"]][1]) as (local, monitor, verifier):
                configured = settings.model_copy(update={"database_path": local.database_path,
                                                         "fault_database_path": local.fault_database_path})
                blocked = partial(recover, executor=blocked_recovery) if case["id"] == "persistent_auth" else None
                graph = build_graph(monitor, settings=configured, verification_tools=verifier,
                                    diagnostic_node=None if live else demo_diagnose, recovery_node=blocked)
                initial = IncidentState(incident_id=case["id"], user_report=case["report"])
                result = run_graph(graph, initial, case["id"], "gemini" if live else "demo", case["id"])
                monitoring = next((step.state for step in result.steps if step.node == "monitor"), initial)
                actions = [step.update["recovery_action"] for step in result.steps
                           if step.node == "recover" and step.update.get("recovery_action")]
                components = [step.update.get("suspected_component") for step in result.steps if step.node == "diagnose"]
                faults = get_fault_state(local.fault_database_path).model_dump()
                oracle_profile = verifier.check_profile()
                oracle_resolved = not any(faults.values()) and oracle_profile.passed and not oracle_profile.error
                metrics = {
                    "monitoring_correct": monitoring.service_status == case["health"] and
                        monitoring.profile_check is not None and monitoring.profile_check.passed == case["profile_pass"],
                    "diagnosis_correct": components == case["components"],
                    "recovery_correct": actions == case["actions"],
                    "verification_correct": result.state.verification_passed == case["verified"] == oracle_resolved,
                    "outcome_correct": result.state.final_status == case["final_status"] and result.state.incident_resolved == oracle_resolved,
                    "retry_correct": result.state.retry_count == case["retries"],
                }
                rows.append({"scenario": case["id"], **metrics, "passed": all(metrics.values()),
                             "actions": actions, "components": components, "final_status": result.state.final_status,
                             "retry_count": result.state.retry_count, "latency_ms": result.elapsed_ms,
                             "tool_calls": result.state.tool_calls,
                             "extra_monitoring_passes": max(0, sum(s.node == "monitor" for s in result.steps) - 1),
                             "extra_verification_passes": max(0, sum(s.node == "verify" for s in result.steps) - 1 - result.state.retry_count),
                             "remaining_faults": faults, "errors": result.state.errors})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live_gemini" if live else "deterministic_integration",
        "model": settings.llm_model if live else None,
        "limitation": None if live else "Diagnosis uses explicit deterministic rules; these scores do not measure LLM quality.",
        "passed": sum(row["passed"] for row in rows), "total": len(rows),
        "rates": {key: sum(row[key] for row in rows) / len(rows) for key in metrics},
        "scenarios": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call configured Gemini; requires credentials and incurs API usage")
    parser.add_argument("--output", type=Path, help="Write the measured JSON report")
    args = parser.parse_args()
    try:
        report = evaluate(live=args.live)
    except ValueError as exc:
        parser.error(str(exc))
    payload = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    raise SystemExit(0 if report["passed"] == report["total"] else 1)


if __name__ == "__main__":
    main()
