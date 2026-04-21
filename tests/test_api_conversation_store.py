from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.api.conversation_store import ApiConversationStore
from src.api.schemas import ChatMessageModel, ConversationDetailModel


@pytest.mark.unit
class TestApiConversationStore:
    def test_create_and_get_conversation(self, tmp_path: Path):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")

        created = store.create("Fil API")
        fetched = store.get(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.title == "Fil API"

    def test_append_messages_derives_title_when_default(self, tmp_path: Path):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")
        created = store.create()

        updated = store.append_messages(
            created.id,
            [
                ChatMessageModel(
                    id="u1",
                    role="user",
                    content="Comment structurer une API ObsiRAG Expo ?",
                    createdAt="2026-04-16T18:00:00",
                )
            ],
        )

        assert updated.title.startswith("Comment structurer une API ObsiRAG Expo")
        assert len(updated.messages) == 1

    def test_save_markdown_writes_conversation_file(self, tmp_path: Path, tmp_settings):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")
        conversation = ConversationDetailModel(
            id="conv-1",
            title="Mission Artemis",
            updatedAt="2026-04-16T18:00:00",
            draft="",
            messages=[
                ChatMessageModel(
                    id="u1",
                    role="user",
                    content="Parle moi de Artemis II",
                    createdAt="2026-04-16T18:00:00",
                ),
                ChatMessageModel(
                    id="a1",
                    role="assistant",
                    content="Reponse de test",
                    createdAt="2026-04-16T18:00:01",
                ),
            ],
        )

        with patch("src.api.conversation_store.settings", tmp_settings):
            store.upsert(conversation)
            saved_path = store.save_markdown(conversation.id)

        assert saved_path.exists()
        content = saved_path.read_text(encoding="utf-8")
        assert "conversation_id: conv-1" in content
        assert "# Mission Artemis" in content
        assert "### 🤖 Réponse" in content

    def test_save_markdown_reuses_same_file_for_same_conversation(self, tmp_path: Path, tmp_settings):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")
        conversation = ConversationDetailModel(
            id="conv-stable",
            title="Mission Artemis",
            updatedAt="2026-04-16T18:00:00",
            draft="",
            messages=[
                ChatMessageModel(
                    id="u1",
                    role="user",
                    content="Parle moi de Artemis II",
                    createdAt="2026-04-16T18:00:00",
                ),
                ChatMessageModel(
                    id="a1",
                    role="assistant",
                    content="Premiere reponse",
                    createdAt="2026-04-16T18:00:01",
                ),
            ],
        )

        with patch("src.api.conversation_store.settings", tmp_settings):
            store.upsert(conversation)
            first_path = store.save_markdown(conversation.id)

            conversation.messages.append(
                ChatMessageModel(
                    id="a2",
                    role="assistant",
                    content="Reponse mise a jour",
                    createdAt="2026-04-16T18:00:02",
                )
            )
            store.upsert(conversation)
            second_path = store.save_markdown(conversation.id)

        assert first_path == second_path
        assert list(tmp_settings.conversations_dir.rglob("*.md")) == [first_path]
        content = second_path.read_text(encoding="utf-8")
        assert "Reponse mise a jour" in content

    def test_save_markdown_reuses_existing_markdown_with_same_conversation_id(self, tmp_path: Path, tmp_settings):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")
        conversation = ConversationDetailModel(
            id="conv-reuse",
            title="Titre change",
            updatedAt="2026-04-16T18:00:00",
            draft="",
            messages=[
                ChatMessageModel(
                    id="u1",
                    role="user",
                    content="Question de test",
                    createdAt="2026-04-16T18:00:00",
                )
            ],
        )

        legacy_dir = tmp_settings.conversations_dir / "2026-03"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        legacy_path = legacy_dir / "ancien_nom.md"
        legacy_path.write_text(
            "---\n"
            "tags:\n"
            "  - conversation\n"
            "conversation_id: conv-reuse\n"
            "---\n\n"
            "# Ancien titre\n",
            encoding="utf-8",
        )

        with patch("src.api.conversation_store.settings", tmp_settings):
            store.upsert(conversation)
            saved_path = store.save_markdown(conversation.id)

        assert saved_path == legacy_path
        content = saved_path.read_text(encoding="utf-8")
        assert "# Titre change" in content
        assert "Question de test" in content

    def test_save_report_markdown_writes_insight_file(self, tmp_path: Path, tmp_settings):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")
        conversation = ConversationDetailModel(
            id="conv-2",
            title="Mission Artemis",
            updatedAt="2026-04-16T18:00:00",
            draft="",
            messages=[],
        )

        with patch("src.api.conversation_store.settings", tmp_settings):
            store.upsert(conversation)
            saved_path = store.save_report_markdown(conversation.id, "# Rapport Mission Artemis\n", title="Rapport Mission Artemis")

        assert saved_path.exists()
        assert str(saved_path).startswith(str(tmp_settings.insights_dir))
        assert saved_path.read_text(encoding="utf-8").startswith("# Rapport Mission Artemis")

    def test_save_report_markdown_uses_ascii_safe_filename_for_non_latin_title(self, tmp_path: Path, tmp_settings):
        store = ApiConversationStore(tmp_path / "api" / "conversations.json")
        conversation = ConversationDetailModel(
            id="conv-3",
            title="Mission Artemis",
            updatedAt="2026-04-16T18:00:00",
            draft="",
            messages=[],
        )

        with patch("src.api.conversation_store.settings", tmp_settings):
            store.upsert(conversation)
            saved_path = store.save_report_markdown(
                conversation.id,
                "# Rapport\n",
                title="Lopen_source_est_mort___ce_projet_majeur__Meta暂停与Mercor合作因数据泄露",
            )

        assert saved_path.exists()
        assert "Meta-Mercor" in saved_path.name
        assert "暂停" not in saved_path.name