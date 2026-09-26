import pytest

from evaluation.evaluate import evaluate
from incidentops.config import Settings


def test_ground_truth_evaluation_for_all_scenarios():
    report = evaluate(settings=Settings())
    assert report["passed"] == report["total"] == 7
    assert report["mode"] == "deterministic_integration" and report["model"] is None
    assert "do not measure LLM quality" in report["limitation"]
    assert all(value == 1.0 for value in report["rates"].values())
    assert all(row["extra_monitoring_passes"] == row["extra_verification_passes"] == 0 for row in report["scenarios"])
    assert report["scenarios"][-1]["remaining_faults"]["auth_down"]


def test_live_evaluation_requires_explicit_credentials():
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        evaluate(live=True, settings=Settings(gemini_api_key=""))
