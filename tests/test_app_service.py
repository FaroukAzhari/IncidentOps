import httpx
import pytest
from fastapi.testclient import TestClient

from environment.app_service.main import create_app
from environment.database import get_user, initialize_database
from environment.fault_state import reset_all_faults, set_fault
from incidentops.config import Settings

HEADERS = {"Authorization": "Bearer demo-token"}


@pytest.fixture
def settings(tmp_path):
    config = Settings(database_path=tmp_path / "app.db", fault_database_path=tmp_path / "faults.db")
    initialize_database(config.database_path)
    return config


def success(request):
    assert request.url.path == "/validate"
    assert request.method == "POST"
    assert request.read() == b'{"token":"demo-token"}'
    assert request.extensions["timeout"]["read"] == 2.0
    return httpx.Response(200, json={"valid": True, "username": "demo"})


def test_profile_uses_auth_and_persistent_database(settings):
    with TestClient(create_app(settings, httpx.MockTransport(success))) as client:
        assert client.get("/health").json()["healthy"] is True
        assert client.get("/profile").status_code == 401
        response = client.get("/profile", headers=HEADERS)
        assert response.status_code == 200
        assert response.json() == {"id": 1, "username": "demo", "role": "student"}


@pytest.mark.parametrize("fault,status,detail", [
    ("database_down", 500, "Database connection unavailable"),
    ("wrong_db_config", 500, "Application database configuration invalid"),
    ("api_degraded", 503, "Application running in degraded mode"),
])
def test_faults_and_reset_without_restart(settings, fault, status, detail):
    with TestClient(create_app(settings, httpx.MockTransport(success))) as client:
        set_fault(fault, path=settings.fault_database_path)
        response = client.get("/profile", headers=HEADERS)
        assert response.status_code == status
        assert response.json()["detail"] == detail
        assert client.get("/health").status_code == (503 if fault == "api_degraded" else 200)
        # Configuration faults leave the actual database intact.
        assert get_user("demo", settings.database_path)["username"] == "demo"
        reset_all_faults(settings.fault_database_path)
        assert client.get("/profile", headers=HEADERS).status_code == 200


@pytest.mark.parametrize("upstream,body,expected", [
    (401, {}, 401), (503, {}, 503), (200, {}, 502),
    (200, {"valid": "false", "username": "demo"}, 502),
    (200, {"valid": False, "username": "demo"}, 401),
    (200, {"valid": True, "username": "missing"}, 404),
])
def test_auth_errors_do_not_return_profile(settings, upstream, body, expected):
    transport = httpx.MockTransport(lambda request: httpx.Response(upstream, json=body))
    with TestClient(create_app(settings, transport)) as client:
        assert client.get("/profile", headers=HEADERS).status_code == expected


def test_auth_timeout(settings):
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)
    with TestClient(create_app(settings, httpx.MockTransport(timeout))) as client:
        assert client.get("/profile", headers=HEADERS).status_code == 503


def test_missing_database_is_not_silently_recreated(settings):
    settings.database_path = settings.database_path.parent / "missing.db"
    with TestClient(create_app(settings, httpx.MockTransport(success))) as client:
        assert client.get("/profile", headers=HEADERS).status_code == 500
    assert not settings.database_path.exists()
