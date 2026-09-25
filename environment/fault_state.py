"""Fault flags shared across processes in a separate SQLite control database."""

import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator, Literal

from pydantic import BaseModel

from incidentops.config import load_settings

FaultName = Literal["database_down", "auth_down", "api_degraded", "wrong_db_config"]
FAULT_NAMES = ("database_down", "auth_down", "api_degraded", "wrong_db_config")


class FaultState(BaseModel):
    database_down: bool = False
    auth_down: bool = False
    api_degraded: bool = False
    wrong_db_config: bool = False


@contextmanager
def _connection(path: Path | None) -> Iterator[sqlite3.Connection]:
    target = (path if path is not None else load_settings().fault_database_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target, timeout=2.0)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS faults ("
                "name TEXT PRIMARY KEY, enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)))"
            )
            connection.executemany(
                "INSERT INTO faults (name, enabled) VALUES (?, 0) ON CONFLICT(name) DO NOTHING",
                [(name,) for name in FAULT_NAMES],
            )
        yield connection


def get_fault_state(path: Path | None = None) -> FaultState:
    """Read fresh state; do not cache flags in individual service processes."""
    with _connection(path) as connection:
        rows = dict(connection.execute("SELECT name, enabled FROM faults").fetchall())
    return FaultState(**{name: bool(rows[name]) for name in FAULT_NAMES})


def set_fault(name: FaultName, enabled: bool = True, path: Path | None = None) -> None:
    if name not in FAULT_NAMES:
        raise ValueError(f"Unsupported fault: {name}")
    if not isinstance(enabled, bool):
        raise TypeError("enabled must be a bool")
    with _connection(path) as connection:
        with connection:
            connection.execute("UPDATE faults SET enabled = ? WHERE name = ?", (int(enabled), name))


def reset_all_faults(path: Path | None = None) -> None:
    with _connection(path) as connection:
        with connection:
            connection.execute("UPDATE faults SET enabled = 0")
