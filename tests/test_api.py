from concurrent.futures import ThreadPoolExecutor
from threading import Event

from fastapi.testclient import TestClient

from incidentops.api import create_app
from incidentops.config import Settings
from incidentops.schemas.api import IncidentRequest
from incidentops.workflow import run_incident


def test_api_ui_and_checkpoint_retrieval():
    app = create_app(Settings(gemini_api_key="private-test-key"))
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        config = client.get("/api/config")
        assert "private-test-key" not in config.text and config.json()["gemini_configured"]
        response = client.post("/api/incidents", json={"report": "Profile fails", "scenario": "wrong_db_config", "thread_id": "test-api"})
        assert response.status_code == 200
        body = response.json()
        assert body["state"]["final_status"] == "resolved"
        assert body["steps"][0]["state"]["profile_check"]["passed"] is False
        assert body["state"]["verification_result"]["verified"]
        assert client.get("/api/incidents/test-api").json() == body
        assert client.post("/api/incidents", json={"report": "Again", "thread_id": "test-api"}).status_code == 409
        assert client.get("/api/incidents/missing").status_code == 404
        assert app.state.checkpointer.get_tuple({"configurable": {"thread_id": "test-api"}}) is not None


def test_invalid_requests_do_not_start_workflow():
    calls = []
    def runner(*args):
        calls.append(args)
        raise AssertionError("Should not run")
    with TestClient(create_app(Settings(), runner=runner)) as client:
        for payload in ({"report":" "}, {"report":"x","max_retries":-1}, {"report":"x","max_retries":11},
                        {"report":"x","scenario":"shell"}, {"report":"x","thread_id":"../bad"},
                        {"report":"x","command":"shell"}, {"report":"x","mode":"unknown"}):
            assert client.post("/api/incidents", json=payload).status_code == 422
    assert not calls


def test_backend_error_is_sanitized_and_lock_released():
    def runner(*args):
        raise RuntimeError("private-api-key")
    with TestClient(create_app(Settings(), runner=runner)) as client:
        for _ in range(2):
            response = client.post("/api/incidents", json={"report":"x"})
            assert response.status_code == 500 and "private-api-key" not in response.text


def test_concurrent_workflows_are_rejected_without_blocking_read_routes():
    entered, release = Event(), Event()
    result = run_incident(IncidentRequest(report="test", scenario="healthy"), Settings())
    def runner(*args):
        entered.set()
        assert release.wait(10)
        return result
    with TestClient(create_app(Settings(), runner=runner)) as client, ThreadPoolExecutor() as pool:
        future = pool.submit(client.post, "/api/incidents", json={"report":"one"})
        try:
            assert entered.wait(5)
            assert client.get("/api/config").status_code == 200
            assert client.post("/api/incidents", json={"report":"two"}).status_code == 409
        finally:
            release.set()
        assert future.result().status_code == 200
