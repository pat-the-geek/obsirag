from __future__ import annotations

import json
from pathlib import Path

from src.storage.safe_read import read_text_lines


def list_query_history_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []

    entries: list[dict] = []
    for line in read_text_lines(path, default=[], errors="replace"):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except Exception:
            continue

    entries.sort(key=lambda item: item.get("ts", ""), reverse=True)
    return entries