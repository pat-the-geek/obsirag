from __future__ import annotations

import json
from pathlib import Path

from src.storage.safe_read import read_json_file, read_text_lines


def load_processed_notes_map(path: Path) -> dict:
    payload = _load_json_object(path)
    return payload if isinstance(payload, dict) else {}


def load_processing_status(path: Path) -> dict:
    payload = _load_json_object(path)
    if not isinstance(payload, dict):
        return {}
    return {
        "active": bool(payload.get("active", False)),
        "note": str(payload.get("note", "")),
        "step": str(payload.get("step", "")),
        "log": list(payload.get("log", []) or []),
    }


def read_operational_log_tail(primary_path: Path, fallback_path: Path | None = None, lines: int = 40) -> list[str]:
    paths: list[Path] = [primary_path]
    if fallback_path is not None and fallback_path != primary_path:
        paths.append(fallback_path)

    for candidate in paths:
        if not candidate.exists():
            continue
        content = read_text_lines(candidate, default=[], errors="replace")
        return content[-max(1, int(lines)):]
    return []


def _load_json_object(path: Path):
    if not path.exists():
        return {}
    return read_json_file(path, default={})