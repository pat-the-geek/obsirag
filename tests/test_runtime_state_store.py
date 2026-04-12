from __future__ import annotations

from pathlib import Path

import pytest

from src.ui.runtime_state_store import (
    load_processed_notes_map,
    load_processing_status,
    read_operational_log_tail,
)


@pytest.mark.unit
class TestRuntimeStateStore:
    def test_load_processed_notes_map_returns_dict_or_empty(self, tmp_path: Path):
        path = tmp_path / "processed.json"
        path.write_text('{"a.md": "2026-04-12T10:00:00"}', encoding="utf-8")

        payload = load_processed_notes_map(path)

        assert payload == {"a.md": "2026-04-12T10:00:00"}
        assert load_processed_notes_map(tmp_path / "missing.json") == {}

    @pytest.mark.nrt
    def test_load_processing_status_normalizes_shape(self, tmp_path: Path):
        path = tmp_path / "status.json"
        path.write_text('{"active": true, "note": "n.md", "step": "chunking", "log": ["x"]}', encoding="utf-8")

        payload = load_processing_status(path)

        assert payload == {
            "active": True,
            "note": "n.md",
            "step": "chunking",
            "log": ["x"],
        }

    def test_read_operational_log_tail_supports_fallback(self, tmp_path: Path):
        primary = tmp_path / "missing.log"
        fallback = tmp_path / "fallback.log"
        fallback.write_text("a\nb\nc\n", encoding="utf-8")

        lines = read_operational_log_tail(primary, fallback_path=fallback, lines=2)

        assert lines == ["b", "c"]