from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.storage.json_state import JsonStateStore


class MetricsRecorder:
    def __init__(self, path_provider: Callable[[], Path]) -> None:
        self._path_provider = path_provider

    def _store(self) -> JsonStateStore:
        return JsonStateStore(self._path_provider())

    def _load(self) -> dict:
        return self._store().load({"counters": {}, "summaries": {}})

    def increment(self, metric: str, amount: int = 1) -> None:
        payload = self._load()
        counters = payload.setdefault("counters", {})
        counters[metric] = int(counters.get(metric, 0)) + amount
        self._store().save(payload, ensure_ascii=False, indent=2)

    def observe(self, metric: str, value: float) -> None:
        payload = self._load()
        summaries = payload.setdefault("summaries", {})
        current = summaries.get(metric, {"count": 0, "total": 0.0, "avg": 0.0, "last": 0.0})
        count = int(current.get("count", 0)) + 1
        total = float(current.get("total", 0.0)) + float(value)
        summaries[metric] = {
            "count": count,
            "total": round(total, 3),
            "avg": round(total / count, 3),
            "last": round(float(value), 3),
        }
        self._store().save(payload, ensure_ascii=False, indent=2)