from unittest.mock import Mock

import pytest

from incidentops.agents import diagnostic_agent
from incidentops.config import Settings
from incidentops.schemas.diagnosis import Diagnosis
from incidentops.schemas.verification import CheckResult
from incidentops.tools import recovery_tools


@pytest.fixture
def student3_settings(tmp_path, monkeypatch):
    settings = Settings(
        gemini_api_key="offline-test-key",
        database_path=tmp_path / "app.db",
        fault_database_path=tmp_path / "faults.db",
    )
    monkeypatch.setattr(diagnostic_agent, "load_settings", lambda: settings)
    monkeypatch.setattr(recovery_tools, "load_settings", lambda: settings)
    return settings


@pytest.fixture
def diagnostic_model(student3_settings, monkeypatch):
    """Exercise real diagnosis/state mapping without network calls or credentials."""
    model = Mock()
    model.with_structured_output.return_value = model
    model.invoke.return_value = Diagnosis(
        suspected_component="unknown", probable_cause="No justified recovery action",
        confidence=0.5, evidence=[], needs_more_evidence=False, recommended_action="none",
    )
    monkeypatch.setattr(diagnostic_agent, "ChatGoogleGenerativeAI", Mock(return_value=model))
    return model


@pytest.fixture
def failed_verification():
    tools = Mock()
    for name in ("api_health", "auth_health", "database_health", "login", "profile"):
        getattr(tools, f"check_{name}").return_value = CheckResult(name=name, passed=False, details="Controlled failure")
    return tools
