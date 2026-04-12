from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from src.storage.safe_read import read_json_file


class JsonStateStore:
    def __init__(self, path: Path, *, os_module=os, tempfile_module=tempfile) -> None:
        self._path = path
        self._os = os_module
        self._tempfile = tempfile_module

    def load(self, default: Any):
        if not self._path.exists():
            return default
        return read_json_file(self._path, default=default)

    def save(self, value: Any, *, ensure_ascii: bool = False, indent: int | None = None) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(value, ensure_ascii=ensure_ascii, indent=indent)
        tmp_fd, tmp_path = self._tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with self._os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            self._os.replace(tmp_path, self._path)
        except Exception:
            try:
                self._os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def append_json_line(self, entry: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")