import httpx
import pytest
from fastapi.testclient import TestClient

from environment.app_service.main import create_app
from environment.auth_service.main import create_app as create_auth
from environment.database import initialize_database
from environment.fault_state import set_fault
from incidentops.config import Settings
from incidentops.graph import build_graph
from incidentops.tools.local_monitoring_tools import LocalMonitoringTools


@pytest.mark.parametrize("fault,expected", [
    (None, {"api": True, "auth": True, "database": True}),
    ("auth_down", {"api": True, "auth": False, "database": True}),
    ("database_down", {"api": True, "auth": True, "database": False}),
    ("api_degraded", {"api": False, "auth": True, "database": True}),
    ("wrong_db_config", {"api": True, "auth": True, "database": True}),
])
def test_real_service_contracts_through_unchanged_graph(tmp_path, fault, expected):
    settings = Settings(database_path=tmp_path / "app.db", fault_database_path=tmp_path / "faults.db")
    initialize_database(settings.database_path)
    if fault:
        set_fault(fault, path=settings.fault_database_path)
    with TestClient(create_auth(settings.fault_database_path)) as auth:
        def auth_request(request):
            response = auth.post("/validate", content=request.content, headers={"Content-Type": "application/json"})
            return httpx.Response(response.status_code, json=response.json())
        with TestClient(create_app(settings, httpx.MockTransport(auth_request))) as api:
            api.get("/profile", headers={"Authorization": "Bearer demo-token"})
            def request(request):
                client = auth if request.url.port == 8002 else api
                response = client.get(request.url.path)
                return httpx.Response(response.status_code, json=response.json())
            tools = LocalMonitoringTools(settings, httpx.MockTransport(request))
            result = build_graph(tools=tools).invoke(
                {"incident_id": "test", "user_report": "profile failed"},
                {"configurable": {"thread_id": "local-test"}},
            )
            assert result["service_status"] == expected
            assert result["observation_source"] == "local_services"
            assert not result["errors"]
            assert result["metrics"]["api_response_ms"] >= 0
            assert result["metrics"]["api_requests_total"] >= 2
            assert result["logs"]
            assert "demo-token" not in str(result["logs"])
            if fault == "wrong_db_config":
                assert any("configuration invalid" in line for line in result["logs"])


def test_failed_http_collection_is_unknown_and_sanitized(tmp_path):
    def fail(request):
        raise httpx.ConnectError("secret must not leak", request=request)
    tools = LocalMonitoringTools(Settings(), httpx.MockTransport(fail))
    assert tools.check_auth_health().healthy is None
    assert "secret" not in tools.check_auth_health().error
    assert tools.get_application_logs().error
    assert tools.get_service_metrics().error


def test_malformed_health_not_treated_as_healthy():
    tools = LocalMonitoringTools(Settings(), httpx.MockTransport(
        lambda request: httpx.Response(200, json={"service": "api", "healthy": "false", "status": "healthy"})))
    assert tools.check_api_health().healthy is None
    assert tools.check_api_health().error
