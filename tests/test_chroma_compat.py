from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.ui.chroma_compat import (
    count_notes,
    get_backlinks,
    list_note_folders,
    list_note_tags,
    list_notes_sorted_by_title,
    list_recent_notes,
)


@pytest.mark.unit
class TestChromaCompat:
    def test_count_notes_uses_helper_when_available(self):
        chroma = SimpleNamespace(count_notes=lambda: 12)

        assert count_notes(chroma) == 12

    def test_list_notes_sorted_by_title_uses_helper_when_available(self):
        chroma = SimpleNamespace(list_notes_sorted_by_title=lambda: [{"file_path": "a.md", "title": "A"}])

        assert list_notes_sorted_by_title(chroma) == [{"file_path": "a.md", "title": "A"}]

    def test_list_notes_sorted_by_title_falls_back_to_raw_notes(self):
        chroma = SimpleNamespace(
            list_notes=lambda: [
                {"file_path": "b/Beta.md"},
                {"file_path": "a.md", "title": "Alpha"},
            ]
        )

        notes = list_notes_sorted_by_title(chroma)

        assert [note["file_path"] for note in notes] == ["a.md", "b/Beta.md"]

    def test_list_recent_notes_falls_back_to_date_sort(self):
        chroma = SimpleNamespace(
            list_notes=lambda: [
                {"file_path": "old.md", "date_modified": "2026-04-01T10:00:00"},
                {"file_path": "missing.md", "date_modified": ""},
                {"file_path": "new.md", "date_modified": "2026-04-03T10:00:00"},
            ]
        )

        notes = list_recent_notes(chroma, limit=2)

        assert [note["file_path"] for note in notes] == ["new.md", "old.md"]

    def test_list_note_folders_and_tags_fall_back_to_raw_notes(self):
        chroma = SimpleNamespace(
            list_notes=lambda: [
                {"file_path": "notes/a.md", "tags": ["python", "ia"]},
                {"file_path": "archive/b.md", "tags": ["ia"]},
            ]
        )

        assert list_note_folders(chroma) == ["archive", "notes"]
        assert list_note_tags(chroma) == ["ia", "python"]

    def test_get_backlinks_falls_back_to_wikilink_scan(self):
        chroma = SimpleNamespace(
            list_notes=lambda: [
                {"file_path": "notes/source.md", "wikilinks": ["Target"]},
                {"file_path": "notes/Target.md", "wikilinks": []},
            ]
        )

        notes = get_backlinks(chroma, "notes/Target.md")

        assert notes == [{"file_path": "notes/source.md", "wikilinks": ["Target"]}]