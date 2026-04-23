from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from uuid import uuid4

from src.config import settings
from src.storage.json_state import JsonStateStore
from src.storage.safe_read import read_text_lines
from src.storage.slugify import build_ascii_stem

from .schemas import (
    ChatMessageModel,
    ConversationDetailModel,
    EntityContextModel,
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
        return [
            self._normalize_conversation(ConversationDetailModel.model_validate(item.model_dump()))
            for item in payload.conversations
        ]

    def get(self, conversation_id: str) -> ConversationDetailModel | None:
        return next((item for item in self.list() if item.id == conversation_id), None)

    def repair_unanswered_tail(self, conversation_id: str) -> ConversationDetailModel | None:
        conversation = self.get(conversation_id)
        if conversation is None:
            return None

        original_message_count = len(conversation.messages)
        repaired = self._without_unanswered_tail(conversation)
        if len(repaired.messages) == original_message_count:
            return conversation
        return self.upsert(repaired)

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

    def delete_message(self, conversation_id: str, message_id: str) -> ConversationDetailModel | None:
        conversation = self.get(conversation_id)
        if conversation is None:
            return None

        target_index = next((index for index, message in enumerate(conversation.messages) if message.id == message_id), None)
        if target_index is None:
            return None

        deleted_ids = {message_id}
        target_message = conversation.messages[target_index]
        if target_message.role == "assistant" and target_index > 0:
            previous_message = conversation.messages[target_index - 1]
            if previous_message.role == "user":
                deleted_ids.add(previous_message.id)

        kept_messages = [message for message in conversation.messages if message.id not in deleted_ids]

        conversation.messages = kept_messages
        conversation.updatedAt = datetime.now(UTC).isoformat()
        conversation.lastGenerationStats = self._latest_generation_stats(conversation.messages)
        if conversation.title == "Nouveau fil":
            conversation.title = self._derive_title(conversation.messages)
        return self.upsert(conversation)

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

    def patch_message_entity_contexts(
        self,
        conversation_id: str,
        message_id: str,
        entity_contexts: list,
    ) -> bool:
        conversation = self.get(conversation_id)
        if conversation is None:
            return False
        for msg in conversation.messages:
            if msg.id == message_id:
                msg.entityContexts = [
                    ec if isinstance(ec, EntityContextModel) else EntityContextModel.model_validate(ec)
                    for ec in entity_contexts
                ]
                self.upsert(conversation)
                return True
        return False

    def save_markdown(self, conversation_id: str) -> Path:
        conversation = self.get(conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)

        title = conversation.title.strip() or self._derive_title(conversation.messages)
        slug = self._slugify_title(title, fallback="conversation")
        out_path = self._resolve_saved_conversation_path(conversation_id, slug)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(self._render_conversation_markdown(conversation, title), encoding="utf-8")
        return out_path

    def save_report_markdown(self, conversation_id: str, markdown: str, *, title: str | None = None) -> Path:
        conversation = self.get(conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)

        resolved_title = title.strip() if title and title.strip() else f"Rapport {conversation.title.strip() or self._derive_title(conversation.messages)}"
        month = datetime.now(UTC).strftime("%Y-%m")
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
        slug = self._slugify_title(resolved_title, fallback="rapport")
        out_dir = settings.insights_dir / month
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"rapport_{slug}_{timestamp}.md"
        out_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
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
    def _slugify_title(title: str, *, fallback: str) -> str:
        return build_ascii_stem(title, fallback=fallback, max_length=60, separator="-")

    @staticmethod
    def _conversation_filename(slug: str, conversation_id: str) -> str:
        return f"{slug}_{conversation_id}.md"

    def _resolve_saved_conversation_path(self, conversation_id: str, slug: str) -> Path:
        existing_path = self._find_saved_conversation_markdown(conversation_id)
        if existing_path is not None:
            return existing_path

        month = datetime.now(UTC).strftime("%Y-%m")
        out_dir = settings.conversations_dir / month
        return out_dir / self._conversation_filename(slug, conversation_id)

    def _find_saved_conversation_markdown(self, conversation_id: str) -> Path | None:
        root = settings.conversations_dir
        if not root.exists():
            return None

        for month_dir in sorted((path for path in root.iterdir() if path.is_dir()), reverse=True):
            for path in sorted(month_dir.glob("*.md"), reverse=True):
                if self._read_frontmatter_value(path, "conversation_id") == conversation_id:
                    return path
        return None

    @staticmethod
    def _read_frontmatter_value(path: Path, key: str) -> str | None:
        lines = read_text_lines(path, default=[])
        if not lines or lines[0].strip() != "---":
            return None

        pattern = re.compile(rf"^{re.escape(key)}\s*:\s*(.+?)\s*$")
        for line in lines[1:]:
            stripped = line.strip()
            if stripped == "---":
                break
            match = pattern.match(stripped)
            if match is None:
                continue
            value = match.group(1).strip()
            if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
                value = value[1:-1]
            return value
        return None

    @staticmethod
    def _render_conversation_markdown(conversation: ConversationDetailModel, title: str) -> str:
        lines = [
            "---",
            "tags:",
            "  - conversation",
            "  - obsirag",
            f"conversation_id: {conversation.id}",
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
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _latest_generation_stats(messages: list[ChatMessageModel]):
        for message in reversed(messages):
            if message.role == "assistant" and message.stats is not None:
                return message.stats
        return None

    @staticmethod
    def _normalize_conversation(conversation: ConversationDetailModel) -> ConversationDetailModel:
        for message in conversation.messages:
            if message.role == "assistant" and message.provenance != "web" and not message.sentinel:
                message.queryOverview = None
        if not conversation.title.strip():
            conversation.title = ApiConversationStore._derive_title(conversation.messages)
        return conversation

    @staticmethod
    def _without_unanswered_tail(conversation: ConversationDetailModel) -> ConversationDetailModel:
        kept_messages = list(conversation.messages)
        while kept_messages and kept_messages[-1].role == "user":
            kept_messages.pop()

        if len(kept_messages) == len(conversation.messages):
            return conversation

        conversation.messages = kept_messages
        conversation.updatedAt = datetime.now(UTC).isoformat()
        conversation.lastGenerationStats = ApiConversationStore._latest_generation_stats(conversation.messages)
        if conversation.title == "Nouveau fil":
            conversation.title = ApiConversationStore._derive_title(conversation.messages)
        return conversation
