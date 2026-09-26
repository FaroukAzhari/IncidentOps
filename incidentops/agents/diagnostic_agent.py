from pathlib import Path
from typing import Any

from langchain_anthropic import ChatAnthropic

from incidentops.config import load_settings
from incidentops.schemas.diagnosis import Diagnosis
from incidentops.state import IncidentState


PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "diagnostic.txt"


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def _build_evidence(state: IncidentState) -> str:
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
    settings = load_settings()

    if not settings.anthropic_api_key.get_secret_value():
        return {
            "errors": [
                "Diagnostic Agent: ANTHROPIC_API_KEY is not configured."
            ],
            "execution_history": [
                "Diagnostic Agent could not run because the Anthropic API key is missing."
            ],
        }

    llm = ChatAnthropic(
        model=settings.llm_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
    )

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

    return {
        "suspected_root_cause": (
            f"{diagnosis.suspected_component}: {diagnosis.probable_cause}"
        ),
        "diagnosis_confidence": diagnosis.confidence,
        "diagnosis_evidence": diagnosis.evidence,
        "needs_more_evidence": diagnosis.needs_more_evidence,
        "recommended_action": diagnosis.recommended_action,
        "execution_history": [
            (
                "Diagnostic Agent produced a structured diagnosis "
                f"for {diagnosis.suspected_component} "
                f"with confidence {diagnosis.confidence:.2f}."
            )
        ],
    }