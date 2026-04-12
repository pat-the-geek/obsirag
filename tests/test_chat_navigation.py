from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.ui.chat_navigation import (
    append_loaded_conversation,
    build_chat_navigation_entries,
    build_conversation_source_entries,
    filter_chat_navigation_entries,
    filter_saved_conversations,
    load_saved_conversation,
    list_saved_conversations,
    source_identity_key,
)


@pytest.mark.unit
class TestChatNavigationHelpers:
    def test_build_entries_keeps_latest_turn_first_and_extracts_primary_source(self):
        messages = [
            {"role": "user", "content": "Première question sur Python"},
            {
                "role": "assistant",
                "content": "Réponse 1",
                "sources": [
                    {"metadata": {"file_path": "vault/python.md", "note_title": "Python", "is_primary": False}},
                    {"metadata": {"file_path": "vault/python.md", "note_title": "Python", "is_primary": True}},
                ],
            },
            {"role": "user", "content": "Seconde question sur Rust"},
        ]

        entries = build_chat_navigation_entries(messages)

        assert [entry["turn"] for entry in entries] == [2, 1]
        assert entries[1]["primary_source_title"] == "Python"
        assert entries[1]["source_count"] == 1
        assert entries[0]["primary_source_title"] is None

    def test_filter_entries_matches_query_and_source_title(self):
        entries = [
            {
                "turn": 2,
                "query": "Question sur Rust",
                "preview": "Question sur Rust",
                "source_count": 1,
                "primary_source_title": "Langage Rust",
                "primary_source_path": "vault/rust.md",
            },
            {
                "turn": 1,
                "query": "Question sur Python",
                "preview": "Question sur Python",
                "source_count": 0,
                "primary_source_title": None,
                "primary_source_path": None,
            },
        ]

        assert filter_chat_navigation_entries(entries, "rust") == [entries[0]]
        assert filter_chat_navigation_entries(entries, "python") == [entries[1]]

    def test_build_conversation_source_entries_rolls_up_mentions(self):
        messages = [
            {
                "role": "assistant",
                "sources": [
                    {"metadata": {"file_path": "vault/a.md", "note_title": "Alpha", "is_primary": True}},
                    {"metadata": {"file_path": "vault/b.md", "note_title": "Beta", "is_primary": False}},
                ],
            },
            {
                "role": "assistant",
                "sources": [
                    {"metadata": {"file_path": "vault/a.md", "note_title": "Alpha", "is_primary": False}},
                ],
            },
        ]

        entries = build_conversation_source_entries(messages)

        assert entries[0] == {
            "file_path": "vault/a.md",
            "title": "Alpha",
            "mentions": 2,
            "primary_mentions": 1,
        }

    def test_build_entries_deduplicates_absolute_and_relative_source_paths(self, tmp_path: Path):
        vault = tmp_path / "vault"
        vault.mkdir()
        absolute = vault / "notes" / "python.md"
        absolute.parent.mkdir(parents=True)
        absolute.write_text("# Python", encoding="utf-8")

        with patch("src.ui.chat_navigation.settings", SimpleNamespace(vault=vault)):
            messages = [
                {"role": "user", "content": "Question Python"},
                {
                    "role": "assistant",
                    "content": "Réponse",
                    "sources": [
                        {"metadata": {"file_path": str(absolute), "note_title": "Python", "is_primary": False}},
                        {"metadata": {"file_path": "notes/python.md", "note_title": "Python", "is_primary": True}},
                    ],
                },
            ]

            entries = build_chat_navigation_entries(messages)

        assert entries[0]["source_count"] == 1
        assert entries[0]["primary_source_path"] == "notes/python.md"

    def test_source_identity_key_falls_back_to_title_when_path_is_missing(self):
        key = source_identity_key({"note_title": "Python avancé"})

        assert key == "title:python avancé"

    def test_saved_conversations_are_listed_and_filterable(self, tmp_path: Path):
        root = tmp_path / "conversations"
        month = root / "2026-04"
        month.mkdir(parents=True)
        first = month / "alpha.md"
        first.write_text("# Conversation Alpha\nContenu", encoding="utf-8")
        second = month / "beta.md"
        second.write_text("# Conversation Beta\nContenu", encoding="utf-8")

        vault = tmp_path / "vault"
        vault.mkdir()
        obsirag_root = vault / "obsirag"
        (obsirag_root / "conversations").mkdir(parents=True)
        month.rename(obsirag_root / "conversations" / "2026-04")

        entries = list_saved_conversations(obsirag_root / "conversations", vault_root=vault)

        assert {entry["title"] for entry in entries} == {"Conversation Alpha", "Conversation Beta"}
        assert {entry["file_path"] for entry in entries} == {
            "obsirag/conversations/2026-04/alpha.md",
            "obsirag/conversations/2026-04/beta.md",
        }
        assert filter_saved_conversations(entries, "beta") == [
            next(entry for entry in entries if entry["title"] == "Conversation Beta")
        ]

    def test_load_saved_conversation_restores_user_and_assistant_messages(self, tmp_path: Path):
        path = tmp_path / "conversation.md"
        path.write_text(
            "---\ntags:\n  - conversation\n---\n\n"
            "# Conversation Demo\n\n"
            "## 🧑 Première question\n\n"
            "> Première question complète ?\n\n"
            "### 🤖 Réponse\n\n"
            "Première réponse.\n\n"
            "## 🧑 Deuxième question\n\n"
            "> Deuxième question complète ?\n\n"
            "### 🤖 Réponse\n\n"
            "Deuxième réponse.\n",
            encoding="utf-8",
        )

        messages = load_saved_conversation(path)

        assert messages == [
            {"role": "user", "content": "Première question complète ?"},
            {"role": "assistant", "content": "Première réponse.", "sources": [], "stats": {}},
            {"role": "user", "content": "Deuxième question complète ?"},
            {"role": "assistant", "content": "Deuxième réponse.", "sources": [], "stats": {}},
        ]

    def test_append_loaded_conversation_inserts_separator_before_loaded_messages(self):
        existing = [{"role": "user", "content": "Question active"}]
        loaded = [{"role": "assistant", "content": "Réponse reprise", "sources": [], "stats": {}}]

        merged = append_loaded_conversation(existing, loaded)

        assert merged[0] == existing[0]
        assert merged[1]["role"] == "assistant"
        assert "Conversation reprise" in str(merged[1]["content"])
        assert merged[2] == loaded[0]

    def test_append_loaded_conversation_returns_loaded_messages_when_existing_is_empty(self):
        loaded = [{"role": "assistant", "content": "Réponse reprise", "sources": [], "stats": {}}]

        merged = append_loaded_conversation([], loaded)

        assert merged == loaded

    def test_list_saved_conversations_delegates_without_recursive_rescan(self, tmp_path: Path):
        root = tmp_path / "conversations"
        root.mkdir(parents=True)
        expected = [{
            "title": "Conv",
            "file_path": "obsirag/conversations/2026-04/conv.md",
            "absolute_path": str(root / "2026-04" / "conv.md"),
            "month": "2026-04",
        }]

        with (
            patch("src.ui.chat_navigation.list_saved_conversation_entries", return_value=expected) as delegated,
            patch("pathlib.Path.rglob", side_effect=AssertionError("rglob should not be used")),
        ):
            got = list_saved_conversations(root, limit=5, vault_root=tmp_path)

        delegated.assert_called_once()
        assert got == expected