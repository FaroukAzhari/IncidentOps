"""Independent post-recovery verification using observed, typed results."""

from typing import Any

from incidentops.config import load_settings
from incidentops.schemas.verification import CheckResult, VerificationResult
from incidentops.state import IncidentState
from incidentops.tools.verification_tools import LocalVerificationTools, VerificationTools


def verify(state: IncidentState, *, tools: VerificationTools | None = None) -> dict[str, Any]:
    if state.observation_source != "local_services":
        return {
            "verification_passed": None, "verification_result": None, "incident_resolved": False,
            "execution_history": ["Verification Agent skipped simulated observations; no real resolution claimed."],
        }
    tools = tools or LocalVerificationTools(load_settings())
    checks: list[CheckResult] = []
    errors: list[str] = []
    for name in ("api_health", "auth_health", "database_health", "login", "profile"):
        try:
            result = CheckResult.model_validate(getattr(tools, f"check_{name}")())
            if result.name != name:
                raise ValueError("Unexpected verification check identity")
        except Exception as exc:
            result = CheckResult(name=name, passed=False, details="Verification check unavailable.",
                                 error=f"{name} failed ({type(exc).__name__}).")
        if result.error:
            errors.append(result.error)
        checks.append(result)
    failures = [check.name for check in checks if not check.passed or check.error]
    verified = not failures
    result = VerificationResult(
        verified=verified, checks=checks,
        summary="All five independent checks passed." if verified else "Independent verification failed.",
        remaining_problem=", ".join(failures) or None,
    )
    return {
        "verification_passed": verified, "verification_result": result.model_dump(),
        "incident_resolved": verified,
        "service_status": {check.name.removesuffix("_health"): check.passed for check in checks
                           if check.name.endswith("_health") and not check.error},
        "profile_check": checks[-1].model_dump(), "evidence_source": "verification",
        "collection_errors": errors, "errors": errors,
        "tool_calls": {f"verify.{check.name}": 1 for check in checks},
        "execution_history": [f"Verification Agent: {result.summary}"
                              + (f" Remaining: {result.remaining_problem}." if failures else "")],
    }
