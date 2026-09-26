# IncidentOps

## Student 3 progress: diagnosis and targeted recovery

The local services, SQLite user database, shared fault controller, and real
monitoring adapter are implemented. Student 3 adds Gemini structured diagnosis,
bounded evidence requests, and targeted recovery. Student 2's environment and
monitoring tools are preserved. Verification remains Student 4's responsibility.

From an activated Python 3.12 environment, initialize the database with
`python -m environment.database`. Run these in separate terminals:

```powershell
python -m uvicorn environment.auth_service.main:app --host 127.0.0.1 --port 8002
python -m uvicorn environment.app_service.main:app --host 127.0.0.1 --port 8001
```

In a third terminal:

```powershell
python -m incidentops.main --local
python -m environment.fault_controller inject auth_down
python -m incidentops.main --local "Users cannot log in"
python -m environment.fault_controller reset
```

Without `--local`, the original fixed mock observations remain available.
Restart the main service after code changes. API `/logs` returns the latest 100
in-memory application log entries; `/metrics` returns measured request duration
and request/error counts. These reset when the API restarts. Exercise `/profile`
with the `Authorization: Bearer demo-token` header to generate dependency-failure
evidence. This token is a fixed demo credential, not production authentication.
Monitoring does not itself call `/profile`.

The four supported faults are `auth_down`, `database_down`, `api_degraded`, and
`wrong_db_config`. Faults persist separately in `data/faults.db`. A configuration
fault makes profile requests fail while the independent SQLite probe remains
healthy. Unreachable or invalid observations are recorded as collection errors
and omitted from health state rather than asserted unhealthy.

Database locations and HTTP timeout are configurable through `.env.example`'s
settings. SQLite files and `.env` are ignored by Git. Set `GEMINI_API_KEY` locally
to enable diagnosis in `--local` mode; the offline demo needs no key.

Multi-Agent IT Incident Investigation, Recovery & Verification: a university
LangGraph project. **Current stage: Student 3 diagnosis and recovery.**
The CLI supports diagnosis and recovery against the local test services, or a
fixed offline monitoring fixture. It does not yet independently verify resolution.

## Setup and run

Target: Python 3.12. From the repository root on Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m incidentops.main
.\.venv\Scripts\python.exe -m incidentops.main "Profile requests return HTTP 500" --thread-id incident-001
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

On macOS/Linux use `python3.12 -m venv .venv`, `cp .env.example .env`, and
`.venv/bin/python` in place of `.\.venv\Scripts\python.exe`.
With the virtual environment activated, the entry point is `python -m incidentops.main`.
No API key, Docker, database, or external service is required for the offline demo.
The local mode requires the initialized SQLite database and both running services.
Diagnosis also requires `GEMINI_API_KEY`; without it, diagnosis reports an error
and recovery is skipped. Offline mode never calls Gemini or executes recovery.
The example report does not select a scenario: the same deterministic fixture
always reports simulated API/database health and auth unavailability.

Configuration lives in `incidentops/config.py`. `.env` is ignored by Git.
Existing process environment variables override `.env`. The model defaults to
`gemini-3.5-flash-lite` and maximum recovery attempts to 3. Keep `LLM_MODEL` set
to this model. Local monitoring uses the configured service URLs. Recovery uses
`INCIDENTOPS_FAULT_DATABASE_PATH`, which must match the services' fault store.

## Architecture and current status

```text
START -> monitor -> diagnose -> recover -> verify -> finalize -> END
            ^          |                  placeholder
            +----------+ (more evidence, within budget)
```

Diagnosis can request up to `max_evidence_attempts` additional monitoring passes
(default 2), counted separately from recovery attempts. Each pass refreshes the
baseline snapshot. Exhaustion skips recovery. Failed verification retries and
verified terminal outcomes remain for Student 4.

| Role | Responsibility | Current implementation |
| --- | --- | --- |
| Monitoring | Collect factual health, logs, metrics | Local HTTP/SQLite adapter or deterministic offline mock tools |
| Diagnostic | Infer probable cause using Pydantic structured output | Gemini diagnosis, validated evidence requests, stale diagnosis invalidation |
| Recovery | Execute allowlisted actions and count attempts | Four targeted fault-clearing tools, evidence/source guards, attempt limit |
| Verification | Independently check health and functional behavior | Explicit placeholder |

Stack: Python 3.12, LangGraph, LangChain/Google Gemini, Pydantic, python-dotenv,
pytest, FastAPI, Uvicorn, httpx, and Python's SQLite support. Jinja2 is reserved
for the later UI. Dependencies are pinned in `requirements.txt`.

The Monitoring Agent owns baseline evidence selection and aggregation. It does
not need an LLM to choose these five fixed checks. Its prompt documents the role
and is a future system-prompt resource; it is not currently sent to a model.

## State and node contracts

`IncidentState` is a Pydantic BaseModel. Every node accepts this state and returns
only a dictionary of changed fields. The CLI validates the final checkpoint too;
teammates must validate structured tool/model outputs before returning updates.

| Node | Reads | Writes |
| --- | --- | --- |
| monitor | incident_id, requested_evidence, evidence_attempts | service_status, logs, metrics, monitoring_complete, observation_source, evidence_attempts; new errors/history |
| diagnose | Observations, provenance, errors, user_report | Diagnosis fields, recommended_action, requested_evidence; new errors/history |
| recover | Diagnosis, observation_source, recommendation, attempt budget | recovery_action, recovery_attempts, recovery_result; new history |
| verify | No state fields used by placeholder; future: independent tools/recovery context | Currently new history only; future: verification_passed, incident_resolved |
| finalize | Observation source, diagnosis and recovery outcome | Provisional final_status, incident_resolved=False; new history |

Provisional statuses are `monitoring_only` (offline demo), `diagnosis_failed`,
`evidence_exhausted`, `recovery_skipped`, and `awaiting_verification` (an action
was attempted, whether it succeeded or failed). None proves incident resolution.

`errors` and `execution_history` use append reducers. Return **only new entries**,
not the entire existing list. Other fields use replacement semantics. Health,
logs, and metrics describe the latest collection, preventing stale evidence from
surviving a failed repeated check. Checkpoint history preserves earlier snapshots.
`monitoring_complete` means all checks were attempted, even if some failed.

`service_status` holds known booleans only. Missing keys mean unknown/unavailable
observations, not confirmed unhealthy services. A healthy=False response is valid
evidence; a collection exception/error is recorded separately. All five checks
are attempted independently. Evidence provenance is stored in `observation_source`.

### Monitoring adapter

Implement `MonitoringTools` and pass the instance to `build_graph(tools=adapter)`:

| Method | Return type |
| --- | --- |
| check_api_health / check_auth_health / check_database_health | HealthResult(service, healthy, status_code, details, error) |
| get_application_logs | LogsResult(logs, error) |
| get_service_metrics | MetricsResult(metrics, error) |

Adapters expose `observation_source`: `simulated` for mock tools and
`local_services` for the local adapter. They must enforce finite I/O timeouts. Error-bearing results
are excluded from the current observation snapshot. Exceptions and invalid results
are recorded without preventing remaining checks. Return validated models; do not
put credentials in errors, logs, or tool details because state is visible in the CLI.
`requested_evidence` accepts only `api_health`, `auth_health`, `database_health`,
`application_logs`, and `service_metrics`. It must be nonempty exactly when
`needs_more_evidence` is true; it never executes arbitrary commands.

### Structured outputs

`Diagnosis` maps `probable_cause` to `suspected_root_cause`, `confidence` to
`diagnosis_confidence`, `evidence` to `diagnosis_evidence`, and the two identically
named fields to `needs_more_evidence` and `recommended_action`. Include
`suspected_component` in the root-cause description, for example
`"auth: connection refused"`. Diagnosis uses
`ChatGoogleGenerativeAI.with_structured_output(Diagnosis)` with the configured
Gemini model. Missing credentials, model failures, and invalid output clear the
previous diagnosis and recommendation so checkpoint replay cannot act on them.

`RecoveryResult.action` maps to `recovery_action`; `succeeded` and `details` map
to a readable `recovery_result`, for example `"failed: dependency unavailable"`.
Only a real attempted action increments `recovery_attempts`. Action success is
not independent verification. Recovery requires local-service evidence and a
current diagnosis that does not request more evidence. Skipped recovery clears
the previous action/result without incrementing the attempt count.

## Checkpointing and visible state changes

The CLI prints initial state, each node's partial update, and final state. Each
graph has a retained `MemorySaver`, optionally supplied by the caller:

```python
from langgraph.checkpoint.memory import MemorySaver
from incidentops.graph import build_graph
from incidentops.state import IncidentState

saver = MemorySaver()
graph = build_graph(checkpointer=saver)
config = {"configurable": {"thread_id": "incident-001"}}
initial = IncidentState(incident_id="incident-001", user_report="Login failed")
result = graph.invoke(initial.model_dump(), config)
print(graph.get_state(config).values)
print(list(graph.get_state_history(config)))
```

Reuse the **same graph/checkpointer and thread ID in the same process** to inspect
an incident. Use different thread IDs for different incidents. A new CLI process
creates a new saver; reusing its thread ID does not restore an old process's state.
MemorySaver is in-memory checkpointing, not durable storage or cross-process memory.
Reinvoking the graph starts another traversal and appends history; it is not a
read-only checkpoint lookup. Do not replay a full prior state into append reducers.

## Team handoff and remaining course requirements

| Student | Ownership |
| --- | --- |
| 1 | Skeleton, shared state/config, graph/checkpointing, monitoring, CLI/tests |
| 2 | Local main/auth services, SQLite, faults, logs/metrics, real monitoring adapter |
| 3 | Diagnostic and Recovery Agents/tools, structured output, attempt accounting, bounded evidence routing |
| 4 | Verification Agent, conditional recovery loop, UI, evaluation and demo |

Implemented rubric foundations: typed state with varied data and nullable fields,
partial updates, MemorySaver/thread IDs, specialized observation tools, visible
state evolution, structured diagnosis, targeted recovery, and bounded evidence
routing. Remaining work includes independent verification, verification-driven
retries, UI, evaluation, and the final demonstration. Automated tests stub Gemini
and exercise the real monitoring/recovery paths without credentials or network calls.

`environment/` contains runnable main/auth FastAPI services and local fault control.
`evaluation/incidents.json` is intentionally empty and the evaluation harness is
not implemented. There is no IncidentOps HTTP API or web UI yet.
See [HANDOFF.md](HANDOFF.md) for the Student 4 handoff and sequential Git workflow.
