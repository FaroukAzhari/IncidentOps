"""Local SQLite storage. Initialize explicitly with python -m environment.database."""

import sqlite3
from contextlib import closing
from pathlib import Path

from incidentops.config import load_settings


def database_path(path: Path | None = None) -> Path:
    return (path if path is not None else load_settings().database_path).resolve()


def initialize_database(path: Path | None = None) -> Path:
    """Create the users table and seed a demo user without replacing existing data."""
    target = database_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target, timeout=2.0)) as connection:
        with connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS users ("
                "id INTEGER PRIMARY KEY, "
                "username TEXT NOT NULL UNIQUE, "
                "role TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO users (username, role) VALUES (?, ?) "
                "ON CONFLICT(username) DO NOTHING",
                ("demo", "student"),
            )
    return target


def get_user(username: str, path: Path | None = None) -> dict[str, int | str] | None:
    """Read a user; a missing database raises instead of silently creating a file."""
    uri = database_path(path).as_uri() + "?mode=rw"
    with closing(sqlite3.connect(uri, uri=True, timeout=2.0)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT id, username, role FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row is not None else None


if __name__ == "__main__":
    location = initialize_database()
    print(f"Database ready: {location}")
    print(f"Demo user: {get_user('demo', location)}")
