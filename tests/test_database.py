import sqlite3
from contextlib import closing

import pytest

from environment.database import get_user, initialize_database


def test_initialization_persists_user_and_preserves_existing_data(tmp_path):
    path = tmp_path / "data" / "test.db"
    initialize_database(path)
    assert get_user("demo", path) == {"id": 1, "username": "demo", "role": "student"}
    with closing(sqlite3.connect(path)) as connection:
        with connection:
            connection.execute("UPDATE users SET role = 'operator' WHERE username = 'demo'")
    initialize_database(path)
    assert get_user("demo", path)["role"] == "operator"
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_unknown_user_and_sql_input_do_not_match_demo(tmp_path):
    path = initialize_database(tmp_path / "test.db")
    assert get_user("missing", path) is None
    assert get_user("' OR 1=1 --", path) is None


def test_read_does_not_create_missing_database(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        get_user("demo", path)
    assert not path.exists()
