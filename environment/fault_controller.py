"""Controlled fault injection for the local demo, without stopping real processes."""

import argparse
from pathlib import Path

from environment.fault_state import FAULT_NAMES, get_fault_state, reset_all_faults, set_fault


def inject_database_failure(path: Path | None = None) -> None:
    set_fault("database_down", path=path)


def inject_auth_failure(path: Path | None = None) -> None:
    set_fault("auth_down", path=path)


def inject_api_failure(path: Path | None = None) -> None:
    set_fault("api_degraded", path=path)


def inject_config_failure(path: Path | None = None) -> None:
    set_fault("wrong_db_config", path=path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect or change local demo fault flags.")
    parser.add_argument("action", choices=("status", "inject", "reset"))
    parser.add_argument("fault", nargs="?", choices=FAULT_NAMES)
    args = parser.parse_args()
    if args.action == "inject":
        if args.fault is None:
            parser.error("inject requires a fault name")
        set_fault(args.fault)
    else:
        if args.fault is not None:
            parser.error("only inject accepts a fault name")
        if args.action == "reset":
            reset_all_faults()
    print(get_fault_state().model_dump_json(indent=2))


if __name__ == "__main__":
    main()
