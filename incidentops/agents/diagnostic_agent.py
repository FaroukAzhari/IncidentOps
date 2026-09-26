from pathlib import Path
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from incidentops.config import Settings, load_settings
from incidentops.schemas.diagnosis import Diagnosis
from incidentops.state import IncidentState


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "diagnostic.txt"


def _load_prompt() -> str:
    """Load the Diagnostic Agent system instructions."""
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_evidence(state: IncidentState) -> str:
    """Convert the monitoring snapshot into evidence for the diagnostic model."""
    return f"""
Incident ID: {state.incident_id}

User report:
{state.user_report}

Current service health:
{state.service_status}

Application logs:
{state.logs if state.evidence_source == 'monitoring' else 'Prior monitoring logs omitted; use fresh verification below.'}

Service metrics:
{state.metrics if state.evidence_source == 'monitoring' else {}}

Current profile probe:
{state.profile_check.model_dump() if state.profile_check else None}

Latest evidence source: {state.evidence_source}
Latest verification:
{state.verification_result.model_dump() if state.verification_result else None}

Monitoring source:
{state.observation_source}

Monitoring errors:
{state.collection_errors}
""".strip()


def diagnose(state: IncidentState, *, settings: Settings | None = None) -> dict[str, Any]:
    """Diagnose current evidence; never retain an actionable stale diagnosis."""
    cleared = {
        "suspected_root_cause": None,
        "suspected_component": None,
        "diagnosis_confidence": None,
        "diagnosis_evidence": [],
        "needs_more_evidence": None,
        "requested_evidence": [],
        "recommended_action": None,
    }

    # The default mock demonstration must remain offline and cannot drive recovery.
    if state.observation_source == "simulated":
        return {
            **cleared,
            "execution_history": ["Diagnostic Agent skipped simulated observations (offline demo)."],
        }

    settings = settings or load_settings()

    # Do not attempt an LLM call when the Gemini API key is unavailable.
    if not settings.gemini_api_key.get_secret_value():
        return {
            **cleared,
            "errors": [
                "Diagnostic Agent: GEMINI_API_KEY is not configured."
            ],
            "execution_history": [
                "Diagnostic Agent could not run because the Gemini API key is missing."
            ],
        }

    calls = {}
    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            google_api_key=settings.gemini_api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        structured_llm = llm.with_structured_output(Diagnosis)
        prompt = _load_prompt()
        evidence = _build_evidence(state)
        calls = {"diagnose.llm": 1}
        diagnosis = structured_llm.invoke([SystemMessage(content=prompt), HumanMessage(content=evidence)])
        diagnosis = Diagnosis.model_validate(diagnosis)
    except Exception as exc:
        return {
            **cleared,
            "tool_calls": calls,
            "errors": [
                f"Diagnostic Agent failed ({type(exc).__name__})."
            ],
            "execution_history": [
                "Diagnostic Agent failed while generating the diagnosis."
            ],
        }

    # Return only the IncidentState fields updated by the Diagnostic Agent.
    return {
        "suspected_component": diagnosis.suspected_component,
        "tool_calls": calls,
        "suspected_root_cause": (
            f"{diagnosis.suspected_component}: {diagnosis.probable_cause}"
        ),
        "diagnosis_confidence": diagnosis.confidence,
        "diagnosis_evidence": diagnosis.evidence,
        "needs_more_evidence": diagnosis.needs_more_evidence,
        "requested_evidence": diagnosis.requested_evidence,
        "recommended_action": diagnosis.recommended_action,
        "execution_history": [
            (
                "Diagnostic Agent produced a structured diagnosis "
                f"for {diagnosis.suspected_component} "
                f"with confidence {diagnosis.confidence:.2f}."
            )
        ],
    }
