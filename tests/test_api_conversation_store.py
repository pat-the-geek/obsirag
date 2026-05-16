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
        assert "# Mission Artemis" in content
        assert "### 🤖 Réponse" in content

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

    def test_list_recovers_conversations_from_saved_markdown_when_json_missing(self, tmp_path: Path, tmp_settings):
        conversations_root = tmp_settings.conversations_dir / "2026-05"
        conversations_root.mkdir(parents=True, exist_ok=True)
        md = conversations_root / "restored_demo.md"
        md.write_text(
            """---
conversation_id: restore-123
created_at: '2026-05-16T06:43:38Z'
closed_at: '2026-05-16T06:44:45Z'
turns_history:
  - role: user
    content: Bonjour, que sais-tu de ce sujet ?
  - role: assistant
    content: Voici un résumé rapide.
---

# Investigation : Conversation restaurée
""",
            encoding="utf-8",
        )

        store = ApiConversationStore(tmp_path / "api" / "conversations.json")

        with patch("src.api.conversation_store.settings", tmp_settings):
            items = store.list()

        assert len(items) == 1
        assert items[0].id == "restore-123"
        assert items[0].title == "Investigation : Conversation restaurée"
        assert len(items[0].messages) == 2
        assert (tmp_path / "api" / "conversations.json").exists()

    def test_resync_from_saved_markdown_adds_missing_conversations(self, tmp_path: Path, tmp_settings):
        with patch("src.api.conversation_store.settings", tmp_settings):
            store = ApiConversationStore(tmp_path / "api" / "conversations.json")
            store.create("Fil local")

            conversations_root = tmp_settings.conversations_dir / "2026-05"
            conversations_root.mkdir(parents=True, exist_ok=True)
            md = conversations_root / "resync_demo.md"
            md.write_text(
                """---
conversation_id: resync-123
created_at: '2026-05-16T06:43:38Z'
closed_at: '2026-05-16T06:44:45Z'
turns_history:
  - role: user
    content: Question de test
  - role: assistant
    content: Réponse de test
---

# Investigation : Conversation resync
""",
                encoding="utf-8",
            )

            stats = store.resync_from_saved_markdown()
            items = store.list()

        assert stats["recovered"] == 1
        assert stats["added"] == 1
        assert stats["updated"] == 0
        assert len(items) == 2
        assert any(item.id == "resync-123" for item in items)