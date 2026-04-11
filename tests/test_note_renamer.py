from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.learning.note_renamer import AutoLearnNoteRenamer


@pytest.mark.unit
class TestAutoLearnNoteRenamer:
    def test_rename_note_in_vault_aborts_when_destination_exists(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        renamer = AutoLearnNoteRenamer(owner)
        source = Path(tmp_settings.vault) / "Old Title.md"
        target = Path(tmp_settings.vault) / "New Title.md"
        source.write_text("body", encoding="utf-8")
        target.write_text("body", encoding="utf-8")

        result = renamer.rename_note_in_vault(source, "New Title", "Old Title.md")

        assert result is None
        owner._indexer.index_note.assert_not_called()

    def test_update_frontmatter_title_replaces_or_creates_title(self, tmp_path):
        owner = MagicMock()
        owner._fm_end.side_effect = lambda content: content.find("\n---\n", 3)
        renamer = AutoLearnNoteRenamer(owner)
        with_title = tmp_path / "with_title.md"
        without_frontmatter = tmp_path / "without_frontmatter.md"
        with_title.write_text("---\ntitle: Ancien\ntags:\n- x\n---\nBody", encoding="utf-8")
        without_frontmatter.write_text("Body", encoding="utf-8")

        renamer._update_frontmatter_title(with_title, "Nouveau")
        renamer._update_frontmatter_title(without_frontmatter, "Cree")

        assert "title: Nouveau" in with_title.read_text(encoding="utf-8")
        assert without_frontmatter.read_text(encoding="utf-8").startswith("---\ntitle: Cree\n---\n")

    def test_update_vault_wikilinks_rewrites_aliases_and_headings(self, tmp_path):
        owner = MagicMock()
        renamer = AutoLearnNoteRenamer(owner)
        target = tmp_path / "New Title.md"
        target.write_text("skip", encoding="utf-8")
        linked = tmp_path / "Linked.md"
        linked.write_text(
            "[[Old Title]] [[Old Title|alias]] [[Old Title#Section]] [[Other]]",
            encoding="utf-8",
        )

        updated_files = renamer._update_vault_wikilinks(
            tmp_path,
            "Old Title",
            "New Title",
            skip_file=target,
        )

        content = linked.read_text(encoding="utf-8")

        assert updated_files == 1
        assert "[[New Title]]" in content
        assert "[[New Title|alias]]" in content
        assert "[[New Title#Section]]" in content
        owner._indexer.index_note.assert_called_once_with(linked)

    def test_migrate_processed_map_moves_existing_entry(self, tmp_path):
        owner = MagicMock()
        owner._load_processed.return_value = {"Old Title.md": "2026-04-11T10:00:00"}
        renamer = AutoLearnNoteRenamer(owner)
        new_abs = tmp_path / "folder" / "New Title.md"
        new_abs.parent.mkdir(parents=True)
        new_abs.write_text("body", encoding="utf-8")

        renamer._migrate_processed_map(tmp_path, "Old Title.md", new_abs)

        owner._save_processed.assert_called_once_with({"folder/New Title.md": "2026-04-11T10:00:00"})
