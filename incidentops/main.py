"""Run with python -m incidentops.main [report] [--thread-id ID]."""

import argparse
import json
from uuid import uuid4

from pydantic import ValidationError

from incidentops.config import load_settings
from incidentops.graph import build_graph
from incidentops.state import IncidentState


def main() -> None:
    parser = argparse.ArgumentParser(description="IncidentOps Student 1: simulated monitoring")
    parser.add_argument("report", nargs="?", default="Users cannot log into the application.")
    parser.add_argument("--thread-id", help="Checkpoint thread identifier (defaults to incident UUID)")
    args = parser.parse_args()
    if not args.report.strip() or (args.thread_id is not None and not args.thread_id.strip()):
        parser.error("report and thread ID must not be blank")
    try:
        settings = load_settings()
        state = IncidentState(incident_id=str(uuid4()), user_report=args.report,
                              max_recovery_attempts=settings.max_recovery_attempts)
    except ValidationError as exc:
        parser.error(str(exc))
    config = {"configurable": {"thread_id": args.thread_id or state.incident_id}}
    graph = build_graph()
    print("SIMULATED observations; diagnosis/recovery/verification are placeholders.")
    print(f"Thread: {config['configurable']['thread_id']}")
    print("Initial state:", state.model_dump_json(indent=2))
    for update in graph.stream(state.model_dump(), config=config, stream_mode="updates"):
        print(json.dumps(update, indent=2))
    final = IncidentState.model_validate(graph.get_state(config).values)
    print("Final state:", final.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
