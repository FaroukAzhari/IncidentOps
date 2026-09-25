"""Configuration is loaded explicitly, never during module import."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    anthropic_api_key: SecretStr = SecretStr("")
    llm_model: str = "claude-haiku-4-5"
    max_recovery_attempts: int = Field(default=3, gt=0)
    api_url: str = "http://localhost:8001"
    auth_url: str = "http://localhost:8002"
    database_path: Path = PROJECT_ROOT / "data" / "incidentops.db"
    fault_database_path: Path = PROJECT_ROOT / "data" / "faults.db"
    http_timeout_seconds: float = Field(default=2.0, gt=0, le=30)


def load_settings(env_file: Path | None = None) -> Settings:
    """Read project .env; already-set environment variables take precedence."""
    load_dotenv(env_file or Path(__file__).resolve().parents[1] / ".env")
    return Settings(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "claude-haiku-4-5"),
        max_recovery_attempts=os.getenv("INCIDENTOPS_MAX_RECOVERY_ATTEMPTS", "3"),
        api_url=os.getenv("INCIDENTOPS_API_URL", "http://localhost:8001"),
        auth_url=os.getenv("INCIDENTOPS_AUTH_URL", "http://localhost:8002"),
        database_path=PROJECT_ROOT / Path(os.getenv("INCIDENTOPS_DATABASE_PATH", "data/incidentops.db")),
        fault_database_path=PROJECT_ROOT / Path(os.getenv("INCIDENTOPS_FAULT_DATABASE_PATH", "data/faults.db")),
        http_timeout_seconds=os.getenv("INCIDENTOPS_HTTP_TIMEOUT_SECONDS", "2"),
    )
