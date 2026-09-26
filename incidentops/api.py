"""Local course-demo backend. Run on 127.0.0.1, not as a public service."""

from collections import OrderedDict
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.memory import MemorySaver

from incidentops.config import Settings, load_settings
from incidentops.demo import SCENARIOS
from incidentops.schemas.api import IncidentRequest, IncidentResponse
from incidentops.workflow import run_incident

STATIC = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None, *, runner=run_incident) -> FastAPI:
    app = FastAPI(title="IncidentOps", version="1.0.0")
    runs: OrderedDict[str, IncidentResponse] = OrderedDict()
    saver = MemorySaver()
    lock = Lock()
    app.state.checkpointer = saver
    app.state.runs = runs
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    def config():
        current = settings or load_settings()
        return {"model": current.llm_model, "gemini_configured": bool(current.gemini_api_key.get_secret_value()),
                "max_retries": current.max_retries,
                "scenarios": [{"id": name, "label": value[0]} for name, value in SCENARIOS.items()]}

    @app.post("/api/incidents", response_model=IncidentResponse)
    def start(request: IncidentRequest):
        # Both services and their fault store are shared in live mode. A single
        # process/worker serializes runs; the synchronous route runs in a threadpool.
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "Another workflow is running. Try again when it finishes.")
        try:
            if request.thread_id in runs:
                raise HTTPException(409, "Thread ID already exists. Use GET to inspect it or choose a new ID.")
            result = runner(request, settings or load_settings(), saver)
            runs[result.thread_id] = result
            if len(runs) > 100:
                expired, _ = runs.popitem(last=False)
                saver.delete_thread(expired)
            return result
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(500, "Workflow could not start. Check the local service configuration.") from None
        finally:
            lock.release()

    @app.get("/api/incidents/{thread_id}", response_model=IncidentResponse)
    def get_incident(thread_id: str):
        result = runs.get(thread_id)
        if result is None:
            raise HTTPException(404, "Incident not found in this server process.")
        return result

    return app


app = create_app()
