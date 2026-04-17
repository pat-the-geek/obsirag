from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.config import settings
from src.storage.json_state import JsonStateStore

from .schemas import (
    ChatMessageModel,
    ConversationDetailModel,
    StoredConversationCollectionModel,
    StoredConversationModel,
)


class ApiConversationStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or settings.api_conversations_file
        self._store = JsonStateStore(self._path)

    def list(self) -> list[ConversationDetailModel]:
        payload = StoredConversationCollectionModel.model_validate(
            self._store.load({"conversations": [], "updatedAt": datetime.now(UTC).isoformat()})
        )
        return [ConversationDetailModel.model_validate(item.model_dump()) for item in payload.conversations]

    def get(self, conversation_id: str) -> ConversationDetailModel | None:
        return next((item for item in self.list() if item.id == conversation_id), None)

    def create(self, title: str | None = None) -> ConversationDetailModel:
        conversation = ConversationDetailModel(
            id=uuid4().hex,
            title=(title or "Nouveau fil").strip() or "Nouveau fil",
            updatedAt=datetime.now(UTC).isoformat(),
            draft="",
            messages=[],
        )
        self.upsert(conversation)
        return conversation

    def delete(self, conversation_id: str) -> bool:
        items = self.list()
        kept = [item for item in items if item.id != conversation_id]
        deleted = len(kept) != len(items)
        if deleted:
            self._save_all(kept)
        return deleted

    def upsert(self, conversation: ConversationDetailModel) -> ConversationDetailModel:
        items = self.list()
        updated = False
        new_items: list[ConversationDetailModel] = []
        for item in items:
            if item.id == conversation.id:
                new_items.append(self._normalize_conversation(conversation))
                updated = True
            else:
                new_items.append(item)
        if not updated:
            new_items.insert(0, self._normalize_conversation(conversation))
        self._save_all(new_items)
        return self._normalize_conversation(conversation)

    def append_messages(
        self,
        conversation_id: str,
        messages: list[ChatMessageModel],
        *,
        draft: str = "",
        last_generation_stats=None,
    ) -> ConversationDetailModel:
        conversation = self.get(conversation_id)
        if conversation is None:
            conversation = self.create()
            conversation.id = conversation_id
        conversation.messages.extend(messages)
        conversation.draft = draft
        conversation.updatedAt = datetime.now(UTC).isoformat()
        if last_generation_stats is not None:
            conversation.lastGenerationStats = last_generation_stats
        if conversation.title == "Nouveau fil":
            conversation.title = self._derive_title(conversation.messages)
        return self.upsert(conversation)

    def save_markdown(self, conversation_id: str) -> Path:
        conversation = self.get(conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)

        title = conversation.title.strip() or self._derive_title(conversation.messages)
        month = datetime.now(UTC).strftime("%Y-%m")
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
        slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-")[:60] or "conversation"
        out_dir = settings.conversations_dir / month
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{slug}_{timestamp}.md"

        lines = [
            "---",
            "tags:",
            "  - conversation",
            "  - obsirag",
            "---",
            "",
            f"# {title}",
            "",
        ]
        for message in conversation.messages:
            if message.role == "user":
                lines.extend([f"## 🧑 {message.content[:120]}", "", f"> {message.content}", ""])
            elif message.role == "assistant":
                lines.extend(["### 🤖 Réponse", "", message.content, ""])
        out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return out_path

    def _save_all(self, conversations: list[ConversationDetailModel]) -> None:
        payload = StoredConversationCollectionModel(
            conversations=[
                StoredConversationModel.model_validate(self._normalize_conversation(item).model_dump(mode="json"))
                for item in conversations
            ],
            updatedAt=datetime.now(UTC).isoformat(),
        )
        self._store.save(payload.model_dump(mode="json"), ensure_ascii=False, indent=2)

    @staticmethod
    def _derive_title(messages: list[ChatMessageModel]) -> str:
        for message in messages:
            if message.role == "user" and message.content.strip():
                content = " ".join(message.content.split())
                return content[:60] + ("…" if len(content) > 60 else "")
        return "Nouveau fil"

    @staticmethod
    def _normalize_conversation(conversation: ConversationDetailModel) -> ConversationDetailModel:
        if not conversation.title.strip():
            conversation.title = ApiConversationStore._derive_title(conversation.messages)
        return conversation
