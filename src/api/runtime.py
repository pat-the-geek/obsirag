from __future__ import annotations

from threading import Event, Lock, Thread

from src.services import ServiceManager
from src.config import settings
from src.storage.json_state import JsonStateStore

_manager: ServiceManager | None = None
_lock = Lock()
_init_thread: Thread | None = None
_init_done = Event()
_init_error: Exception | None = None


def _startup_store() -> JsonStateStore:
    return JsonStateStore(settings.startup_status_file)


def _write_startup_snapshot(*, ready: bool, current_step: str = "", error: str | None = None, steps: list[str] | None = None) -> None:
    _startup_store().save(
        {
            "ready": ready,
            "steps": list(steps or []),
            "current_step": current_step,
            "error": error,
        },
        ensure_ascii=False,
    )


def _run_init() -> None:
    global _manager, _init_error
    try:
        _manager = ServiceManager()
        _init_error = None
    except Exception as exc:  # noqa: BLE001
        _init_error = exc
        _write_startup_snapshot(ready=False, error=str(exc), current_step="Erreur de démarrage")
    finally:
        _init_done.set()


def ensure_service_manager_started() -> None:
    global _init_thread, _init_error
    if _manager is not None:
        return
    with _lock:
        if _manager is not None or _init_thread is not None:
            return
        _init_error = None
        _init_done.clear()
        _write_startup_snapshot(ready=False, current_step="Initialisation du runtime ObsiRAG")
        _init_thread = Thread(target=_run_init, daemon=True, name="obsirag-api-service-init")
        _init_thread.start()


def get_service_manager() -> ServiceManager:
    global _manager
    if _manager is not None:
        return _manager
    ensure_service_manager_started()
    _init_done.wait()
    if _manager is None:
        detail = str(_init_error) if _init_error is not None else "ServiceManager unavailable"
        raise RuntimeError(detail)
    return _manager
