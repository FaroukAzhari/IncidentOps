from pathlib import Path
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI

from incidentops.config import load_settings
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

Current service health:
{state.service_status}

Application logs:
{state.logs}

Service metrics:
{state.metrics}

Monitoring source:
{state.observation_source}

Monitoring errors:
{state.errors}
""".strip()


def diagnose(state: IncidentState) -> dict[str, Any]:
    """Diagnose the incident from monitoring evidence using structured LLM output."""
    settings = load_settings()

    # Do not attempt an LLM call when the Gemini API key is unavailable.
    if not settings.gemini_api_key.get_secret_value():
        return {
            "errors": [
                "Diagnostic Agent: GEMINI_API_KEY is not configured."
            ],
            "execution_history": [
                "Diagnostic Agent could not run because the Gemini API key is missing."
            ],
        }

    # Use the configured Gemini model for deterministic structured diagnosis.
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        google_api_key=settings.gemini_api_key.get_secret_value(),
    )

    # Force the model response to follow the existing Diagnosis Pydantic schema.
    structured_llm = llm.with_structured_output(Diagnosis)

    prompt = _load_prompt()
    evidence = _build_evidence(state)

    try:
        diagnosis = structured_llm.invoke(
            f"""
{prompt}

MONITORING EVIDENCE
-------------------
{evidence}

Return the structured diagnosis now.
"""
        )
    except Exception as exc:
        return {
            "errors": [
                f"Diagnostic Agent: {type(exc).__name__}: {exc}"
            ],
            "execution_history": [
                "Diagnostic Agent failed while generating the diagnosis."
            ],
        }

    # Return only the IncidentState fields updated by the Diagnostic Agent.
    return {
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

    