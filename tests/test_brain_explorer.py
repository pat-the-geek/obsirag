from __future__ import annotations

from datetime import datetime

import pytest

from src.ui.brain_explorer import (
    build_centrality_spotlight,
    build_folder_summary,
    build_recent_notes,
    build_tag_summary,
    build_type_summary,
    filter_brain_notes,
)


@pytest.mark.unit
class TestBrainExplorerHelpers:
    def test_filter_brain_notes_applies_folder_tag_text_and_recency(self):
        notes = [
            {
                "title": "Python avancé",
                "file_path": "notes/python.md",
                "folder": "notes",
                "tags": ["ia", "python"],
                "date_modified": "2026-04-10T10:00:00",
            },
            {
                "title": "Rust système",
                "file_path": "archives/rust.md",
                "folder": "archives",
                "tags": ["rust"],
                "date_modified": "2026-01-10T10:00:00",
            },
        ]

        filtered = filter_brain_notes(
            notes,
            selected_folders=["notes"],
            selected_tags=["python"],
            search_text="avancé",
            modified_within_days=30,
            now=datetime(2026, 4, 20, 10, 0, 0),
        )

        assert filtered == [notes[0]]

    def test_build_recent_notes_orders_by_date_descending(self):
        notes = [
            {"title": "A", "file_path": "a.md", "date_modified": "2026-04-01T10:00:00"},
            {"title": "B", "file_path": "b.md", "date_modified": "2026-04-10T10:00:00"},
            {"title": "C", "file_path": "c.md", "date_modified": ""},
        ]

        recent = build_recent_notes(notes, limit=2)

        assert [note["file_path"] for note in recent] == ["b.md", "a.md"]

    def test_build_centrality_spotlight_enriches_visible_nodes_only(self):
        notes = [
            {"title": "Alpha", "file_path": "alpha.md", "tags": ["x"], "date_modified": "2026-04-10T10:00:00"},
        ]
        top_connected = [
            {"file_path": "alpha.md", "score": 0.9},
            {"file_path": "missing.md", "score": 0.7},
        ]

        spotlight = build_centrality_spotlight(notes, top_connected)

        assert spotlight == [
            {
                "file_path": "alpha.md",
                "title": "Alpha",
                "score": 0.9,
                "date_modified": "2026-04-10",
                "tags": ["x"],
            }
        ]

    def test_folder_and_tag_summaries_count_filtered_notes(self):
        notes = [
            {"folder": "notes", "tags": ["python", "ia"]},
            {"folder": "notes", "tags": ["python"]},
            {"folder": "archives", "tags": ["rust"]},
        ]

        assert build_folder_summary(notes) == [
            {"folder": "notes", "count": 2},
            {"folder": "archives", "count": 1},
        ]
        assert build_tag_summary(notes)[:3] == [
            {"tag": "python", "count": 2},
            {"tag": "ia", "count": 1},
            {"tag": "rust", "count": 1},
        ]

    def test_filter_brain_notes_supports_type_filter(self):
        notes = [
            {"title": "A", "file_path": "notes/a.md", "folder": "notes", "tags": []},
            {"title": "B", "file_path": "obsirag/insights/b.md", "folder": "obsirag/insights", "tags": []},
        ]

        filtered = filter_brain_notes(
            notes,
            selected_folders=["Tous"],
            selected_tags=[],
            selected_types=["insight"],
        )

        assert [note["file_path"] for note in filtered] == ["obsirag/insights/b.md"]

    def test_build_type_summary_counts_note_types(self):
        notes = [
            {"file_path": "notes/a.md"},
            {"file_path": "obsirag/insights/b.md"},
            {"file_path": "obsirag/insights/c.md"},
        ]

        assert build_type_summary(notes) == [
            {"type": "insight", "count": 2},
            {"type": "user", "count": 1},
        ]