from __future__ import annotations

import errno
import os
from datetime import UTC, datetime
from typing import Any

from src.config import settings
from src.storage.json_state import JsonStateStore

_WORKER_HEARTBEAT_TTL = 180  # secondes — tolérance doublée pour les passes entity_notes longues


def _store() -> JsonStateStore:
    return JsonStateStore(settings.autolearn_runtime_file)


def _worker_heartbeat_alive(payload: dict) -> bool:
    """Retourne True si le worker a écrit son état dans les _WORKER_HEARTBEAT_TTL secondes."""
    updated_at = payload.get("updatedAt")
    if not updated_at:
        return False
    try:
        dt = datetime.fromisoformat(updated_at)
        age_s = (datetime.now(UTC) - dt).total_seconds()
        return age_s < _WORKER_HEARTBEAT_TTL
    except Exception:
        return False


def load_autolearn_runtime_state() -> dict[str, Any]:
    payload = _store().load({
        "managedBy": "none",
        "running": False,
        "pid": None,
        "startedAt": None,
        "updatedAt": None,
        "nextRunAt": None,
    })

    if not payload.get("running"):
        return payload

    # Vérification primaire : heartbeat récent (robuste aux redémarrages du container)
    if _worker_heartbeat_alive(payload):
        return payload

    # Vérification secondaire : PID valide dans le namespace courant
    pid = payload.get("pid")
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
            return payload  # processus existant, heartbeat périmé mais PID ok
        except OSError as exc:
            if exc.errno == errno.EPERM:
                return payload  # processus existe, pas de permission de le signaler
            # ESRCH : processus inexistant
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
