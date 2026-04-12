from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_text_file(path: Path, *, default: str = "", errors: str = "strict") -> str:
    try:
        return path.read_text(encoding="utf-8", errors=errors)
    except Exception:
        return default


def read_text_lines(path: Path, *, default: list[str] | None = None, errors: str = "replace") -> list[str]:
    content = read_text_file(path, default="", errors=errors)
    if not content:
        return list(default or [])
    return content.splitlines()


def read_json_file(path: Path, *, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
