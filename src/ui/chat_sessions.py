from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def ensure_chat_state(state: dict | None) -> dict:
    if isinstance(state, dict):
        threads = state.get("threads")
        current_thread_id = state.get("current_thread_id")
        if isinstance(threads, list) and threads:
            sanitized = [_sanitize_thread(thread) for thread in threads]
            known_ids = {thread["id"] for thread in sanitized}
            if current_thread_id not in known_ids:
                current_thread_id = sanitized[0]["id"]
            return {
                "threads": sanitized,
                "current_thread_id": current_thread_id,
            }

    initial_thread = create_chat_thread()
    return {
        "threads": [initial_thread],
        "current_thread_id": initial_thread["id"],
    }


def create_chat_thread(
    *,
    title: str | None = None,
    messages: list[dict] | None = None,
    draft: str = "",
) -> dict:
    thread_messages = list(messages or [])
    return {
        "id": uuid4().hex,
        "title": _derive_thread_title(title, thread_messages),
        "messages": thread_messages,
        "draft": draft,
        "updated_at": _now_iso(),
    }


def get_current_thread(state: dict) -> dict:
    if isinstance(state, dict) and isinstance(state.get("threads"), list) and state.get("threads"):
        chat_state = state
    else:
        chat_state = ensure_chat_state(state)
    current_thread_id = chat_state["current_thread_id"]
    current = next(
        (thread for thread in chat_state["threads"] if thread["id"] == current_thread_id),
        None,
    )
    if current is not None:
        return current
    fallback = chat_state["threads"][0]
    chat_state["current_thread_id"] = fallback["id"]
    return fallback


def update_current_thread(
    state: dict | None,
    *,
    messages: list[dict] | None = None,
    draft: str | None = None,
    title: str | None = None,
) -> dict:
    chat_state = ensure_chat_state(state)
    current = get_current_thread(chat_state)
    current["messages"] = list(messages if messages is not None else current.get("messages", []))
    current["draft"] = draft if draft is not None else current.get("draft", "")
    current["title"] = _derive_thread_title(title or current.get("title"), current["messages"])
    current["updated_at"] = _now_iso()
    return chat_state


def create_new_thread(state: dict | None, *, title: str | None = None) -> dict:
    chat_state = ensure_chat_state(state)
    thread = create_chat_thread(title=title)
    chat_state["threads"].insert(0, thread)
    chat_state["current_thread_id"] = thread["id"]
    return chat_state


def create_thread_from_messages(
    state: dict | None,
    *,
    messages: list[dict],
    title: str | None = None,
    draft: str = "",
) -> dict:
    chat_state = ensure_chat_state(state)
    thread = create_chat_thread(title=title, messages=messages, draft=draft)
    chat_state["threads"].insert(0, thread)
    chat_state["current_thread_id"] = thread["id"]
    return chat_state


def switch_thread(state: dict | None, thread_id: str) -> dict:
    chat_state = ensure_chat_state(state)
    if any(thread["id"] == thread_id for thread in chat_state["threads"]):
        chat_state["current_thread_id"] = thread_id
    return chat_state


def delete_thread(state: dict | None, thread_id: str) -> dict:
    chat_state = ensure_chat_state(state)
    chat_state["threads"] = [thread for thread in chat_state["threads"] if thread["id"] != thread_id]
    if not chat_state["threads"]:
        replacement = create_chat_thread()
        chat_state["threads"] = [replacement]
        chat_state["current_thread_id"] = replacement["id"]
        return chat_state

    if chat_state["current_thread_id"] == thread_id:
        chat_state["current_thread_id"] = chat_state["threads"][0]["id"]
    return chat_state


def list_thread_summaries(state: dict | None, limit: int = 8) -> list[dict[str, str | int | bool]]:
    chat_state = ensure_chat_state(state)
    current_thread_id = chat_state["current_thread_id"]
    summaries: list[dict[str, str | int | bool]] = []
    threads = sorted(
        chat_state["threads"],
        key=lambda thread: thread.get("updated_at", ""),
        reverse=True,
    )
    for thread in threads[:limit]:
        messages = thread.get("messages", [])
        user_messages = [message for message in messages if message.get("role") == "user"]
        summaries.append({
            "id": thread["id"],
            "title": thread.get("title") or "Nouveau fil",
            "preview": _thread_preview(messages),
            "message_count": len(messages),
            "turn_count": len(user_messages),
            "updated_at": str(thread.get("updated_at") or ""),
            "is_current": thread["id"] == current_thread_id,
        })
    return summaries


def _sanitize_thread(thread: dict) -> dict:
    messages = thread.get("messages") if isinstance(thread.get("messages"), list) else []
    return {
        "id": str(thread.get("id") or uuid4().hex),
        "title": _derive_thread_title(thread.get("title"), messages),
        "messages": list(messages),
        "draft": str(thread.get("draft") or ""),
        "updated_at": str(thread.get("updated_at") or _now_iso()),
    }


def _derive_thread_title(title: str | None, messages: list[dict]) -> str:
    candidate = " ".join((title or "").split())
    if candidate and candidate.lower() != "nouveau fil":
        return candidate[:80]

    for message in messages:
        if message.get("role") == "user":
            content = " ".join(str(message.get("content") or "").split())
            if content:
                return content[:60] + ("…" if len(content) > 60 else "")
    return "Nouveau fil"


def _thread_preview(messages: list[dict], limit: int = 72) -> str:
    for message in reversed(messages):
        content = " ".join(str(message.get("content") or "").split())
        if content:
            return content[:limit] + ("…" if len(content) > limit else "")
    return "Fil vide"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()