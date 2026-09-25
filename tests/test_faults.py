import os
import subprocess
import sys

import pytest

from environment.fault_controller import (
    inject_api_failure, inject_auth_failure, inject_config_failure, inject_database_failure,
)
from environment.fault_state import get_fault_state, reset_all_faults, set_fault


def test_faults_are_independent_and_reset_together(tmp_path):
    path = tmp_path / "faults.db"
    assert not any(get_fault_state(path).model_dump().values())
    inject_auth_failure(path)
    assert get_fault_state(path).model_dump() == {
        "database_down": False, "auth_down": True,
        "api_degraded": False, "wrong_db_config": False,
    }
    inject_database_failure(path)
    inject_api_failure(path)
    inject_config_failure(path)
    assert all(get_fault_state(path).model_dump().values())
    set_fault("auth_down", False, path)
    assert not get_fault_state(path).auth_down
    assert get_fault_state(path).database_down
    reset_all_faults(path)
    assert not any(get_fault_state(path).model_dump().values())


def test_other_process_observes_fault_changes(tmp_path):
    path = tmp_path / "faults.db"
    inject_auth_failure(path)
    environment = dict(os.environ, INCIDENTOPS_FAULT_DATABASE_PATH=str(path))
    result = subprocess.run(
        [sys.executable, "-m", "environment.fault_controller", "status"],
        env=environment, capture_output=True, text=True, check=True, timeout=10,
    )
    import json
    assert json.loads(result.stdout)["auth_down"] is True
    subprocess.run(
        [sys.executable, "-m", "environment.fault_controller", "reset"],
        env=environment, capture_output=True, text=True, check=True, timeout=10,
    )
    assert not get_fault_state(path).auth_down


def test_invalid_fault_does_not_create_storage(tmp_path):
    path = tmp_path / "faults.db"
    with pytest.raises(ValueError):
        set_fault("unknown", path=path)
    assert not path.exists()
