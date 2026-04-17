from __future__ import annotations

from threading import Lock

from src.services import ServiceManager

_manager: ServiceManager | None = None
_lock = Lock()


def get_service_manager() -> ServiceManager:
    global _manager
    if _manager is not None:
        return _manager
    with _lock:
        if _manager is None:
            _manager = ServiceManager()
    return _manager
