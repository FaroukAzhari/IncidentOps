import pytest
from pydantic import ValidationError

from incidentops.config import load_settings


def test_dotenv_and_environment_precedence(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("INCIDENTOPS_MAX_RECOVERY_ATTEMPTS", raising=False)
    monkeypatch.setenv("LLM_MODEL", "process-model")
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=\nLLM_MODEL=file-model\nINCIDENTOPS_MAX_RECOVERY_ATTEMPTS=4\n")
    settings = load_settings(env_file)
    assert settings.anthropic_api_key.get_secret_value() == ""
    assert settings.llm_model == "process-model"
    assert settings.max_recovery_attempts == 4


@pytest.mark.parametrize("value", ["0", "invalid"])
def test_invalid_recovery_configuration(tmp_path, monkeypatch, value):
    monkeypatch.setenv("INCIDENTOPS_MAX_RECOVERY_ATTEMPTS", value)
    with pytest.raises(ValidationError):
        load_settings(tmp_path / "missing.env")
