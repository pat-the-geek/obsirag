from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from src.ui.insights_browser import (
    build_artifact_entries,
    build_artifact_expander_label,
    build_artifact_panel_caption,
    build_month_options,
    build_query_day_options,
    filter_markdown_entries,
    filter_queries,
    load_query_history,
)


@pytest.mark.unit
class TestInsightsBrowserHelpers:
    def test_build_artifact_entries_orders_by_date_and_deduplicates_paths(self):
        notes = [
            {"file_path": "obsirag/insights/b.md", "date_modified": "2026-04-11T10:00:00"},
            {"file_path": "obsirag/insights/a.md", "date_modified": "2026-04-10T10:00:00"},
            {"file_path": "obsirag/insights/b.md", "date_modified": "2026-04-09T10:00:00"},
        ]

        entries = build_artifact_entries(notes)

        assert [path for path, _mtime in entries] == [
            "obsirag/insights/b.md",
            "obsirag/insights/a.md",
        ]

    def test_build_artifact_expander_label_formats_date_and_fallback(self):
        ts = datetime(2026, 4, 11, 10, 30).timestamp()

        assert build_artifact_expander_label("obsirag/insights/demo.md", ts, "💡") == "💡 demo — 2026-04-11 10:30"
        assert build_artifact_expander_label("obsirag/insights/demo.md", 0.0, "💡") == "💡 demo — date inconnue"

    def test_build_artifact_panel_caption_formats_counts_label_and_subpath(self):
        caption = build_artifact_panel_caption(3, 8, "artefact(s)", "obsirag/insights/")

        assert caption == "3 / 8 artefact(s) · Visibles dans Obsidian sous `obsirag/insights/`"

    def test_build_month_options_returns_descending_months(self):
        entries = [
            ("/tmp/a.md", datetime(2026, 4, 10).timestamp()),
            ("/tmp/b.md", datetime(2026, 3, 5).timestamp()),
            ("/tmp/c.md", datetime(2026, 4, 1).timestamp()),
        ]

        assert build_month_options(entries) == ["Tous", "2026-04", "2026-03"]

    def test_build_month_options_ignores_unknown_timestamps(self):
        entries = [
            ("/tmp/a.md", 0.0),
            ("/tmp/b.md", datetime(2026, 3, 5).timestamp()),
        ]

        assert build_month_options(entries) == ["Tous", "2026-03"]

    def test_filter_markdown_entries_filters_by_month_and_content(self):
        entries = [
            ("/tmp/Alpha.md", datetime(2026, 4, 10).timestamp()),
            ("/tmp/Beta.md", datetime(2026, 3, 5).timestamp()),
        ]

        filtered = filter_markdown_entries(
            entries,
            search_text="recherche",
            month_filter="2026-04",
            content_lookup=lambda path, _mtime: "mot cle recherche" if path.endswith("Alpha.md") else "rien",
        )

        assert filtered == [entries[0]]

    def test_load_query_history_ignores_invalid_json_and_sorts(self):
        lines = [
            '{"ts":"2026-04-10T10:00:00","query":"plus ancien"}',
            'not json',
            '{"ts":"2026-04-11T10:00:00","query":"plus récent"}',
        ]

        queries = load_query_history(lines)

        assert [q["query"] for q in queries] == ["plus récent", "plus ancien"]

    def test_query_filters_apply_text_and_day(self):
        queries = [
            {"ts": "2026-04-11T10:00:00", "query": "parle moi de python"},
            {"ts": "2026-04-10T10:00:00", "query": "parle moi de rust"},
        ]

        assert build_query_day_options(queries) == ["Toutes", "2026-04-11", "2026-04-10"]
        assert filter_queries(queries, search_text="python", day_filter="Toutes") == [queries[0]]
        assert filter_queries(queries, search_text="parle", day_filter="2026-04-10") == [queries[1]]

    def test_build_artifact_entries_from_indexed_notes_never_uses_recursive_rglob(self):
        notes = [
            {"file_path": "obsirag/insights/a.md", "date_modified": "2026-04-10T10:00:00"},
            {"file_path": "obsirag/insights/b.md", "date_modified": "2026-04-11T10:00:00"},
        ]

        with patch("pathlib.Path.rglob", side_effect=AssertionError("rglob should not be used")):
            entries = build_artifact_entries(notes)

        assert [path for path, _ in entries] == ["obsirag/insights/b.md", "obsirag/insights/a.md"]