import pytest
from pydantic import ValidationError

from incidentops.schemas.diagnosis import Diagnosis
from incidentops.state import IncidentState


def test_defaults_and_independent_collections():
    first = IncidentState(incident_id="a", user_report="Login failed")
    second = IncidentState(incident_id="b", user_report="Profile failed")
    assert first.recovery_attempts == 0
    assert first.max_recovery_attempts == 3
    assert not first.monitoring_complete and not first.incident_resolved
    for name in ("suspected_root_cause", "diagnosis_confidence", "needs_more_evidence",
                 "recommended_action", "recovery_action", "recovery_result",
                 "verification_passed", "final_status", "observation_source"):
        assert getattr(first, name) is None
    for name in ("logs", "diagnosis_evidence", "requested_evidence", "errors", "execution_history"):
        getattr(first, name).append("one")
        assert getattr(second, name) == []
    first.service_status["api"] = True
    first.metrics["latency"] = 1.0
    assert second.service_status == second.metrics == {}


@pytest.mark.parametrize("field,value", [
    ("diagnosis_confidence", -0.1), ("diagnosis_confidence", 1.1),
    ("recovery_attempts", -1), ("max_recovery_attempts", 0),
])
def test_invalid_state_bounds(field, value):
    with pytest.raises(ValidationError):
        IncidentState(incident_id="a", user_report="report", **{field: value})


def test_diagnosis_confidence_contract():
    with pytest.raises(ValidationError):
        Diagnosis(suspected_component="auth", probable_cause="unknown", confidence=2,
                  evidence=[], needs_more_evidence=True, recommended_action="none")
