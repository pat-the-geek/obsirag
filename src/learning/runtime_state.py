from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from src.config import settings
from src.storage.json_state import JsonStateStore


def _store() -> JsonStateStore:
    return JsonStateStore(settings.autolearn_runtime_file)


def load_autolearn_runtime_state() -> dict[str, Any]:
    payload = _store().load({
        "managedBy": "none",
        "running": False,
        "pid": None,
        "startedAt": None,
        "updatedAt": None,
        "nextRunAt": None,
    })

    pid = payload.get("pid")
    if payload.get("running") and isinstance(pid, int):
        try:
            os.kill(pid, 0)
        except OSError:
            payload["running"] = False
            payload["nextRunAt"] = None
            _store().save(payload, ensure_ascii=False, indent=2)

    return payload


def save_autolearn_runtime_state(state: dict[str, Any]) -> None:
    snapshot = {
        "managedBy": state.get("managedBy", "none"),
        "running": bool(state.get("running", False)),
        "pid": state.get("pid"),
        "startedAt": state.get("startedAt"),
        "updatedAt": datetime.now(UTC).isoformat(),
        "nextRunAt": state.get("nextRunAt"),
    }
    _store().save(snapshot, ensure_ascii=False, indent=2)


def _last_run_store() -> JsonStateStore:
    return JsonStateStore(settings.data_dir / "stats" / "autolearn_last_run.json")


def save_last_run_status(status: str) -> None:
    """Persiste le statut du dernier cycle autolearn (success | error)."""
    _last_run_store().save({
        "status": status,
        "at": datetime.now(UTC).isoformat(),
    }, ensure_ascii=False, indent=2)


def load_last_run_status() -> dict[str, Any]:
    return _last_run_store().load({"status": "unknown", "at": None})
