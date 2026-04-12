from __future__ import annotations

from pathlib import Path

import pytest

from src.ui.query_history_store import list_query_history_entries


@pytest.mark.unit
class TestQueryHistoryStore:
    def test_list_query_history_entries_sorts_desc_and_skips_invalid_lines(self, tmp_path: Path):
        path = tmp_path / "queries.jsonl"
        path.write_text(
            "{\"ts\": \"2026-04-11T10:00:00\", \"query\": \"Q1\"}\n"
            "not-json\n"
            "{\"ts\": \"2026-04-12T10:00:00\", \"query\": \"Q2\"}\n",
            encoding="utf-8",
        )

        entries = list_query_history_entries(path)

        assert [entry["query"] for entry in entries] == ["Q2", "Q1"]

    def test_list_query_history_entries_returns_empty_when_file_missing(self, tmp_path: Path):
        entries = list_query_history_entries(tmp_path / "missing.jsonl")

        assert entries == []