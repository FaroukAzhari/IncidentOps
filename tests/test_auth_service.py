import pytest
from fastapi.testclient import TestClient

from environment.auth_service.main import create_app
from environment.fault_state import reset_all_faults, set_fault


def test_auth_healthy_and_validates_demo_token(tmp_path):
    with TestClient(create_app(tmp_path / "faults.db")) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"service": "auth", "healthy": True, "status": "healthy"}
        response = client.post("/validate", json={"token": "demo-token"})
        assert response.status_code == 200
        assert response.json() == {"valid": True, "username": "demo"}


def test_running_service_observes_injection_and_reset(tmp_path):
    path = tmp_path / "faults.db"
    with TestClient(create_app(path)) as client:
        assert client.get("/health").status_code == 200
        set_fault("auth_down", path=path)
        assert client.get("/health").status_code == 503
        assert client.get("/health").json()["healthy"] is False
        assert client.post("/validate", json={"token": "demo-token"}).status_code == 503
        reset_all_faults(path)
        assert client.get("/health").status_code == 200
        assert client.post("/validate", json={"token": "demo-token"}).status_code == 200


def test_bad_token_rejected_without_logging_token(tmp_path, caplog):
    with TestClient(create_app(tmp_path / "faults.db")) as client:
        assert client.post("/validate", json={"token": "private-invalid-token"}).status_code == 401
        assert "private-invalid-token" not in caplog.text
        assert client.post("/validate", json={}).status_code == 422


@pytest.mark.parametrize("fault", ["database_down", "wrong_db_config", "api_degraded"])
def test_auth_independent_of_other_faults(tmp_path, fault):
    path = tmp_path / "faults.db"
    set_fault(fault, path=path)
    with TestClient(create_app(path)) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/validate", json={"token": "demo-token"}).status_code == 200


def test_unreadable_fault_storage_returns_service_error(tmp_path):
    path = tmp_path / "faults.db"
    path.write_text("not a sqlite database")
    with TestClient(create_app(path)) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/validate", json={"token": "demo-token"}).status_code == 503
