# Student 1 handoff to Student 2

## Implemented

- Python 3.12 skeleton, pinned dependencies, centralized `.env` configuration.
- Shared Pydantic state, partial updates, append-only error/history reducers.
- Five stable monitoring interfaces with typed results and deterministic mock data.
- Specialized Monitoring Agent with independent failure handling.
- Runnable graph with MemorySaver, thread IDs, honest placeholder nodes, CLI snapshots.
- Offline tests for contracts, failure handling, graph execution and checkpoints.

## Preserve unless discussed with the team

State field meanings, graph node names, node partial-update contracts, tool
interfaces, and responsibility boundaries. Return only new errors/history entries.
Health/logs/metrics replace the previous snapshot. Unknown health is omitted,
not reported as false. Never let Monitoring populate diagnosis or resolution.

## Student 2 implementation

1. Implement main FastAPI service on port 8001 and auth service on port 8002.
2. Add SQLite, reproducible fault state/controller, real logs and metrics.
3. Implement the MonitoringTools adapter with bounded HTTP/database calls and
   `observation_source="local_services"`; inject it into the graph. Keep mock tools
   available for offline tests. Centralize additional settings in config.py.
4. Replace `diagnose` with evidence-based Anthropic structured output using the
   Diagnosis schema. Validate and map outputs as documented in README.
5. Coordinate conditional evidence requests with Student 3. Bound evidence loops
   separately from recovery retries. Do not add an unbounded monitor/diagnose loop.

Student 3 owns recovery actions/attempts and evidence routing. Student 4 owns
verification, final retry routing, UI and evaluation. The current finalizer always
returns `monitoring_only`; it must be updated with real terminal semantics when
those behaviors are implemented. Successful recovery tools alone must not resolve
an incident.

## Run and validate

Use README setup commands, then:

```powershell
.\.venv\Scripts\python.exe -m incidentops.main
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

No key or service is needed for the current tests/CLI. No real recovery has been
performed. Mock evidence is fixed regardless of the incident report.

## Sequential main workflow

Only one student works/pushes at a time. Once the GitHub remote is configured,
each student starts with `git pull origin main`. Before handing off, run the CLI,
tests and dependency checks, update requirements/documentation as needed, commit,
push and tell the next student what changed.

Initial publication commands (replace the URL with the team's repository):

```powershell
git remote add origin https://github.com/OWNER/REPOSITORY.git
git add .
git commit -m "Initialize IncidentOps architecture and monitoring agent"
git push -u origin main
```

No remote destination was supplied during implementation; publication is pending.
