from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.ui.path_resolver import normalize_vault_relative_path, resolve_vault_path


@pytest.mark.unit
class TestUiPathResolver:
    def test_resolve_relative_path_against_current_vault(self, tmp_settings):
        with patch("src.ui.path_resolver.settings", SimpleNamespace(vault=tmp_settings.vault)):
            resolved = resolve_vault_path("obsirag/insights/demo.md")

        assert resolved == tmp_settings.vault / "obsirag/insights/demo.md"

    def test_normalize_absolute_path_inside_current_vault(self, tmp_settings):
        note_path = tmp_settings.vault / "notes" / "python.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("# Python", encoding="utf-8")

        with patch("src.ui.path_resolver.settings", SimpleNamespace(vault=tmp_settings.vault)):
            normalized = normalize_vault_relative_path(str(note_path))

        assert normalized == "notes/python.md"

    def test_resolve_rebases_stale_absolute_path_to_current_vault(self, tmp_settings, tmp_path: Path):
        note_path = tmp_settings.vault / "obsirag" / "insights" / "demo.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text("# Demo", encoding="utf-8")
        stale_absolute = tmp_path / "ancien-coffre" / "obsirag" / "insights" / "demo.md"

        with patch("src.ui.path_resolver.settings", SimpleNamespace(vault=tmp_settings.vault)):
            resolved = resolve_vault_path(str(stale_absolute))
            normalized = normalize_vault_relative_path(str(stale_absolute))

        assert resolved == note_path
        assert normalized == "obsirag/insights/demo.md"

    def test_normalize_external_absolute_path_keeps_absolute_form(self, tmp_settings, tmp_path: Path):
        external_path = tmp_path / "external" / "note.md"
        external_path.parent.mkdir(parents=True, exist_ok=True)
        external_path.write_text("# Externe", encoding="utf-8")

        with patch("src.ui.path_resolver.settings", SimpleNamespace(vault=tmp_settings.vault)):
            normalized = normalize_vault_relative_path(str(external_path))

        assert normalized == external_path.as_posix()