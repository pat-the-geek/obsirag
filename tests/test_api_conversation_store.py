from __future__ import annotations

from pathlib import Path

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

        from unittest.mock import patch

        with patch("src.api.conversation_store.settings", tmp_settings):
            store.upsert(conversation)
            saved_path = store.save_markdown(conversation.id)

        assert saved_path.exists()
        content = saved_path.read_text(encoding="utf-8")
        assert "# Mission Artemis" in content
        assert "### 🤖 Réponse" in content