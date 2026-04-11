from __future__ import annotations

from datetime import datetime

import pytest

from src.ui.insights_browser import (
    build_month_options,
    build_query_day_options,
    filter_markdown_entries,
    filter_queries,
    load_query_history,
)


@pytest.mark.unit
class TestInsightsBrowserHelpers:
    def test_build_month_options_returns_descending_months(self):
        entries = [
            ("/tmp/a.md", datetime(2026, 4, 10).timestamp()),
            ("/tmp/b.md", datetime(2026, 3, 5).timestamp()),
            ("/tmp/c.md", datetime(2026, 4, 1).timestamp()),
        ]

        assert build_month_options(entries) == ["Tous", "2026-04", "2026-03"]

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