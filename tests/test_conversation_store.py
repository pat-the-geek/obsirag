from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.ui.conversation_store import list_saved_conversation_entries


@pytest.mark.unit
class TestConversationStore:
    @pytest.mark.nrt
    def test_list_saved_conversation_entries_reads_month_folders_and_returns_relative_paths(self, tmp_path: Path):
        vault = tmp_path / "vault"
        root = vault / "obsirag" / "conversations"
        april = root / "2026-04"
        may = root / "2026-05"
        april.mkdir(parents=True)
        may.mkdir(parents=True)

        (april / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
        newest = may / "beta.md"
        newest.write_text("# Beta\n", encoding="utf-8")

        entries = list_saved_conversation_entries(root, vault_root=vault)

        assert entries[0]["title"] == "Beta"
        assert entries[0]["file_path"] == "obsirag/conversations/2026-05/beta.md"
        assert {entry["month"] for entry in entries} == {"2026-04", "2026-05"}

    def test_list_saved_conversation_entries_honors_limit(self, tmp_path: Path):
        root = tmp_path / "conversations"
        month = root / "2026-04"
        month.mkdir(parents=True)
        for index in range(3):
            (month / f"note-{index}.md").write_text(f"# Note {index}\n", encoding="utf-8")

        entries = list_saved_conversation_entries(root, limit=2)

        assert len(entries) == 2

    def test_list_saved_conversation_entries_does_not_use_recursive_rglob_in_nominal_path(self, tmp_path: Path):
        root = tmp_path / "conversations"
        month = root / "2026-04"
        month.mkdir(parents=True)
        (month / "one.md").write_text("# One\n", encoding="utf-8")

        with patch("pathlib.Path.rglob", side_effect=AssertionError("rglob should not be used")):
            entries = list_saved_conversation_entries(root, limit=10)

        assert [entry["title"] for entry in entries] == ["One"]