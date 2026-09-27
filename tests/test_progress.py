"""Operational progress must arrive before completion and preserve run safety."""

from contextlib import contextmanager
import json
import socket
from threading import Event, Thread
from time import monotonic, sleep

import httpx
from fastapi.testclient import TestClient
import uvicorn

from incidentops.api import create_app
from incidentops.config import Settings
from incidentops.schemas.api import IncidentRequest
from incidentops.workflow import run_incident


def test_progress_tracks_actual_tools_and_retry_without_changing_results():
    events = []
    request = IncidentRequest(report="Login and profile fail", scenario="multiple_faults", thread_id="events")
    result = run_incident(request, Settings(), on_event=events.append)
    started = [e["node"] for e in events if e["event"] == "node_started"]
    assert started == [step.node for step in result.steps]
    assert started == ["monitor", "diagnose", "recover", "verify", "retry", "diagnose", "recover", "verify", "finalize"]
    assert events[0]["event"] == "node_started"
    first_step = next(i for i, e in enumerate(events) if e["event"] == "step_completed")
    collected = [e for e in events[:first_step] if e["event"] == "tool_completed"]
    assert len(collected) == 6
    assert any(e["tool"] == "check_auth_health" and e["result"]["healthy"] is False for e in collected)
    assert len([e for e in events if e["event"] == "tool_completed" and e["node"] == "verify"]) == 10
    assert result.state.incident_resolved and result.state.retry_count == 1
    assert events[-1]["step"]["state"] == result.state.model_dump(mode="json")


def test_stream_terminal_result_matches_get_and_rejects_duplicate():
    with TestClient(create_app(Settings())) as client:
        response = client.post("/api/incidents/stream", json={"report": "Login failed", "thread_id": "stream-test"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[0]["event"] == "run_started"
        assert events[-1]["event"] == "run_completed"
        assert events[-1]["result"] == client.get("/api/incidents/stream-test").json()
        assert client.post("/api/incidents/stream", json={"report": "Again", "thread_id": "stream-test"}).status_code == 409
        assert client.post("/api/incidents/stream", json={"report": " "}).status_code == 422


def test_stream_failure_is_sanitized_and_releases_lock():
    def fail(*args, **kwargs):
        raise RuntimeError("private-api-key")
    with TestClient(create_app(Settings(), runner=fail)) as client:
        for _ in range(2):
            response = client.post("/api/incidents/stream", json={"report": "test"})
            assert response.status_code == 200
            assert "private-api-key" not in response.text
            assert json.loads(response.text.splitlines()[-1])["event"] == "run_failed"


@contextmanager
def real_server(app):
    """TestClient buffers streams; a real loopback socket proves incremental delivery."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = monotonic() + 5
        while not server.started and monotonic() < deadline:
            sleep(.01)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()


def test_socket_stream_arrives_before_completion_and_disconnect_keeps_lock():
    entered, release = Event(), Event()
    def paused(request, settings, saver, *, on_event):
        on_event({"event": "node_started", "node": "diagnose"})
        entered.set()
        assert release.wait(10)
        return run_incident(request, settings, saver, on_event=on_event)
    with real_server(create_app(Settings(), runner=paused)) as url, httpx.Client(base_url=url, trust_env=False, timeout=5) as client:
        try:
            with client.stream("POST", "/api/incidents/stream", json={"report": "Test", "thread_id": "disconnect"}) as response:
                lines = response.iter_lines()
                assert json.loads(next(lines))["event"] == "run_started"
                assert json.loads(next(lines))["event"] == "node_started"
                assert entered.wait(1) and not release.is_set()
            # Closing the response must not permit a second concurrent recovery.
            assert client.get("/api/config").status_code == 200
            assert client.post("/api/incidents", json={"report": "Second"}).status_code == 409
            assert client.post("/api/incidents/stream", json={"report": "Second"}).status_code == 409
        finally:
            release.set()
        deadline = monotonic() + 5
        while monotonic() < deadline:
            response = client.get("/api/incidents/disconnect")
            if response.status_code == 200:
                break
            sleep(.02)
        assert response.status_code == 200
        assert response.json()["state"]["incident_resolved"]
