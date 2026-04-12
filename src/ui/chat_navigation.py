from __future__ import annotations

from pathlib import PurePath
from pathlib import Path

from src.config import settings
from src.storage.safe_read import read_text_lines
from src.ui.conversation_store import list_saved_conversation_entries


def build_chat_navigation_entries(messages: list[dict]) -> list[dict[str, int | str | None]]:
    entries: list[dict[str, int | str | None]] = []
    turn = 0

    for index, message in enumerate(messages):
        if message.get("role") != "user":
            continue

        turn += 1
        question = (message.get("content") or "").strip()
        assistant = None
        if index + 1 < len(messages) and messages[index + 1].get("role") == "assistant":
            assistant = messages[index + 1]

        sources = _dedupe_sources(assistant.get("sources") or []) if assistant else []
        primary_source = next(
            (src for src in sources if (src.get("metadata") or {}).get("is_primary")),
            sources[0] if sources else None,
        )
        primary_meta = (primary_source or {}).get("metadata") or {}

        entries.append({
            "turn": turn,
            "query": question,
            "preview": _preview_text(question),
            "source_count": len(sources),
            "primary_source_title": primary_meta.get("note_title") or primary_meta.get("file_path"),
            "primary_source_path": primary_meta.get("file_path"),
        })

    return list(reversed(entries))


def filter_chat_navigation_entries(
    entries: list[dict[str, int | str | None]],
    search_text: str,
    limit: int = 10,
) -> list[dict[str, int | str | None]]:
    search = search_text.strip().lower()
    if not search:
        return entries[:limit]

    filtered = [
        entry for entry in entries
        if search in str(entry.get("query") or "").lower()
        or search in str(entry.get("primary_source_title") or "").lower()
    ]
    return filtered[:limit]


def build_conversation_source_entries(messages: list[dict], limit: int = 8) -> list[dict[str, int | str]]:
    rolled_up: dict[str, dict[str, int | str]] = {}

    for message in messages:
        if message.get("role") != "assistant":
            continue
        for source in _dedupe_sources(message.get("sources") or []):
            metadata = source.get("metadata") or {}
            file_path = metadata.get("file_path")
            if not file_path:
                continue
            entry = rolled_up.setdefault(
                file_path,
                {
                    "file_path": file_path,
                    "title": metadata.get("note_title") or file_path,
                    "mentions": 0,
                    "primary_mentions": 0,
                },
            )
            entry["mentions"] = int(entry["mentions"]) + 1
            if metadata.get("is_primary"):
                entry["primary_mentions"] = int(entry["primary_mentions"]) + 1

    return sorted(
        rolled_up.values(),
        key=lambda entry: (
            int(entry["primary_mentions"]),
            int(entry["mentions"]),
            str(entry["title"]).lower(),
        ),
        reverse=True,
    )[:limit]


def list_saved_conversations(root: Path, limit: int = 12, vault_root: Path | None = None) -> list[dict[str, str]]:
    return list_saved_conversation_entries(
        root,
        limit=limit,
        vault_root=vault_root,
        title_loader=_read_first_heading,
    )


def filter_saved_conversations(entries: list[dict[str, str]], search_text: str) -> list[dict[str, str]]:
    search = search_text.strip().lower()
    if not search:
        return entries
    return [
        entry for entry in entries
        if search in entry["title"].lower() or search in entry["file_path"].lower() or search in entry["month"].lower()
    ]


def load_saved_conversation(path: Path) -> list[dict[str, str | list | dict]]:
    try:
        lines = read_text_lines(path, default=[], errors="replace")
    except OSError:
        return []

    content_lines = _strip_frontmatter(lines)
    messages: list[dict[str, str | list | dict]] = []
    index = 0
    while index < len(content_lines):
        line = content_lines[index]
        if line.startswith("## 🧑 "):
            question, index = _read_saved_user_block(content_lines, index)
            if question:
                messages.append({"role": "user", "content": question})
            continue
        if line.startswith("### 🤖 Réponse"):
            answer, index = _read_saved_assistant_block(content_lines, index)
            if answer:
                messages.append({"role": "assistant", "content": answer, "sources": [], "stats": {}})
            continue
        index += 1
    return messages


def append_loaded_conversation(
    existing_messages: list[dict],
    loaded_messages: list[dict],
) -> list[dict[str, str | list | dict]]:
    if not existing_messages:
        return list(loaded_messages)
    separator = {
        "role": "assistant",
        "content": "---\nConversation reprise depuis un historique sauvegardé.\n---",
        "sources": [],
        "stats": {},
    }
    return list(existing_messages) + [separator] + list(loaded_messages)


def source_identity_key(metadata: dict | None) -> str:
    meta = metadata or {}
    file_path = normalize_source_path(str(meta.get("file_path") or ""))
    note_title = " ".join(str(meta.get("note_title") or "").lower().split())
    if file_path and note_title:
        return f"{file_path}|{note_title}"
    if file_path:
        return file_path
    if note_title:
        return f"title:{note_title}"
    return ""


def normalize_source_path(file_path: str) -> str:
    if not file_path:
        return ""
    normalized = file_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    try:
        path = Path(normalized)
        if path.is_absolute():
            try:
                normalized = str(path.relative_to(settings.vault))
            except ValueError:
                normalized = path.as_posix()
        else:
            normalized = PurePath(normalized).as_posix()
    except Exception:
        normalized = normalized.replace("\\", "/")
    return normalized.lower()


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for source in sources:
        metadata = source.get("metadata") or {}
        source_key = source_identity_key(metadata)
        if not source_key:
            continue
        current = seen.get(source_key)
        if current is None:
            seen[source_key] = source
            continue
        current_primary = bool((current.get("metadata") or {}).get("is_primary"))
        source_primary = bool(metadata.get("is_primary"))
        if source_primary and not current_primary:
            seen[source_key] = source
    return list(seen.values())


def _preview_text(text: str, limit: int = 88) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _read_first_heading(path: Path) -> str:
    try:
        for line in read_text_lines(path, default=[], errors="replace"):
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        return ""
    return ""


def _strip_frontmatter(lines: list[str]) -> list[str]:
    if not lines or lines[0].strip() != "---":
        return lines
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[index + 1:]
    return lines


def _read_saved_user_block(lines: list[str], start_index: int) -> tuple[str, int]:
    heading = lines[start_index][4:].strip()
    index = start_index + 1
    question_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("## 🧑 ") or line.startswith("### 🤖 Réponse"):
            break
        if line.startswith("> "):
            question_lines.append(line[2:])
        index += 1
    question = "\n".join(question_lines).strip() or heading
    return question, index


def _read_saved_assistant_block(lines: list[str], start_index: int) -> tuple[str, int]:
    index = start_index + 1
    answer_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("## 🧑 "):
            break
        answer_lines.append(line)
        index += 1
    return "\n".join(answer_lines).strip(), index