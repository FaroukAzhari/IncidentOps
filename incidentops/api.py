"""Local course-demo backend. Run on 127.0.0.1, not as a public service."""

from collections import OrderedDict
from pathlib import Path
from threading import Lock, Thread
from queue import Empty, Queue
from time import perf_counter
from uuid import uuid4
import json
import httpx
from pydantic import BaseModel, ConfigDict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver

from incidentops.config import Settings, load_settings
from incidentops.demo import SCENARIOS
from incidentops.schemas.api import IncidentRequest, IncidentResponse
from incidentops.workflow import run_incident
from incidentops.tools.functional_checks import check_login, check_profile
from environment.fault_state import FaultName, get_fault_state, reset_all_faults, set_fault

STATIC = Path(__file__).resolve().parent / "static"


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fault: FaultName


def create_app(settings: Settings | None = None, *, runner=run_incident,
               portal_transport: httpx.BaseTransport | None = None) -> FastAPI:
    app = FastAPI(title="IncidentOps", version="1.0.0")
    runs: OrderedDict[str, IncidentResponse] = OrderedDict()
    saver = MemorySaver()
    lock = Lock()
    app.state.checkpointer = saver
    app.state.runs = runs
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def reserve(request: IncidentRequest) -> None:
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Another workflow is running. Try again when it finishes.")
        if request.thread_id in runs:
            lock.release()
            raise HTTPException(409, "Thread ID already exists. Use GET to inspect it or choose a new ID.")

    def remember(result: IncidentResponse) -> None:
        runs[result.thread_id] = result
        if len(runs) > 100:
            expired, _ = runs.popitem(last=False)
            saver.delete_thread(expired)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    def config():
        current = settings or load_settings()
        return {"model": current.llm_model, "gemini_configured": bool(current.gemini_api_key.get_secret_value()),
                "max_retries": current.max_retries,
                "scenarios": [{"id": name, "label": value[0]} for name, value in SCENARIOS.items()]}

    def portal_snapshot():
        current = settings or load_settings()
        login = check_login(current, portal_transport)
        profile = check_profile(current, portal_transport) if login.passed else None
        return {"login": login.model_dump(mode="json"),
                "profile": profile.model_dump(mode="json") if profile else None,
                "ready": bool(login.passed and profile and profile.passed),
                "faults": get_fault_state(current.fault_database_path).model_dump()}

    @app.get("/api/lab/portal")
    def portal():
        """Read-only fixed demo identity probe; the report never creates a fault."""
        return portal_snapshot()

    def change_fault(change):
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "An investigation is running. Change faults after it completes.")
        try:
            current = settings or load_settings()
            change(current.fault_database_path)
            return portal_snapshot()
        finally:
            lock.release()

    @app.post("/api/lab/faults")
    def inject_fault(request: FaultRequest):
        return change_fault(lambda path: set_fault(request.fault, path=path))

    @app.post("/api/lab/reset")
    def clear_faults():
        return change_fault(reset_all_faults)

    @app.post("/api/incidents", response_model=IncidentResponse)
    def start(request: IncidentRequest):
        # Both services and their fault store are shared in live mode. A single
        # process/worker serializes runs; the synchronous route runs in a threadpool.
        reserve(request)
        try:
            result = runner(request, settings or load_settings(), saver)
            remember(result)
            return result
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(500, "Workflow could not start. Check the local service configuration.") from None
        finally:
            lock.release()

    @app.post("/api/incidents/stream")
    def stream(request: IncidentRequest):
        """NDJSON events. Disconnecting stops delivery, not an in-flight recovery.

        The worker retains the run lock until completion and stores the result
        for GET lookup. Execution budgets bound the number of queued events.
        """
        request = request.model_copy(update={"thread_id": request.thread_id or str(uuid4())})
        reserve(request)
        messages: Queue[str | None] = Queue()
        started = perf_counter()

        def publish(event: dict) -> None:
            messages.put(json.dumps({**event, "thread_id": request.thread_id,
                                     "elapsed_ms": round((perf_counter() - started) * 1000, 3)}) + "\n")

        def work() -> None:
            try:
                publish({"event": "run_started", "mode": request.mode,
                         "scenario": request.scenario if request.mode == "demo" else None})
                result = runner(request, settings or load_settings(), saver, on_event=publish)
                remember(result)
                publish({"event": "run_completed", "result": result.model_dump(mode="json")})
            except Exception:
                publish({"event": "run_failed", "message": "Workflow could not complete. Check the local service configuration."})
            finally:
                lock.release()
                messages.put(None)

        def events():
            while True:
                try:
                    item = messages.get(timeout=5)
                except Empty:
                    yield json.dumps({"event": "heartbeat"}) + "\n"
                    continue
                if item is None:
                    break
                yield item

        try:
            Thread(target=work, daemon=True, name=f"incident-{request.thread_id}").start()
        except Exception:
            lock.release()
            raise HTTPException(500, "Workflow could not start.") from None
        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/incidents/{thread_id}", response_model=IncidentResponse)
    def get_incident(thread_id: str):
        result = runs.get(thread_id)
        if result is None:
            raise HTTPException(404, "Incident not found in this server process.")
        return result

    return app


app = create_app()
