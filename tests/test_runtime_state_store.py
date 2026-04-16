from __future__ import annotations

from pathlib import Path

import pytest

from src.ui.runtime_state_store import (
    load_chat_threads_state,
    load_processed_notes_map,
    load_processing_status,
    read_operational_log_tail,
    save_chat_threads_state,
)
from src.ui.chat_sessions import get_current_thread


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

    def test_chat_threads_state_round_trip_restores_messages(self, tmp_path: Path):
        path = tmp_path / "ui" / "chat_threads_state.json"
        state = {
            "threads": [
                {
                    "id": "thread-1",
                    "title": "Conversation test",
                    "messages": [
                        {"role": "user", "content": "Question 1"},
                        {"role": "assistant", "content": "Réponse 1"},
                    ],
                    "draft": "",
                    "last_gen_stats": {"tokens": 12},
                    "updated_at": "2026-04-16T18:00:00+00:00",
                }
            ],
            "current_thread_id": "thread-1",
        }

        saved = save_chat_threads_state(path, state)
        loaded = load_chat_threads_state(path)
        current = get_current_thread(loaded)

        assert path.exists()
        assert loaded == saved
        assert current["messages"][1]["content"] == "Réponse 1"

    def test_load_chat_threads_state_returns_default_shape_when_missing(self, tmp_path: Path):
        loaded = load_chat_threads_state(tmp_path / "missing.json")

        assert "threads" in loaded
        assert len(loaded["threads"]) == 1
        assert loaded["current_thread_id"] == loaded["threads"][0]["id"]