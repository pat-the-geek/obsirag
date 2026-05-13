"""MCP investigation conversation manager.

Manages investigation conversations stored as Markdown notes in
vault/obsirag/conversations/YYYY-MM/.

Each investigation is a controlled Q&A loop (max 3 continue turns)
that lets an external AI client (Claude) persist a quality-check
dialogue against obsirag_ask_rag answers.

Guards:
- Only 1 active investigation at a time per client.
- Hard limit of 3 continue turns after start.
- Auto-finalize after 30 minutes of inactivity.
- Notes are never indexed into the vector store (exclude_from_rag: true).
- Notes are never processed by the autolearner (_is_obsirag_generated covers them).
"""
from __future__ import annotations

import threading
import unicodedata
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter as fm_lib

from src.config import settings
from src.storage.slugify import build_ascii_stem

# ---- Constants ---------------------------------------------------------------

VALID_TRIGGER_REASONS: frozenset[str] = frozenset({
    "sentinel_response",
    "low_confidence",
    "incomplete_coverage",
    "contradictory_sources",
    "unexpected_primary_source",
    "branch_exploration",
})

MAX_TURNS = 3
MAX_TRIGGER_EXPLANATION = 500
MAX_REASONING = 300
MAX_ANSWER_LEN = 4000
AUTO_FINALIZE_SECONDS = 30 * 60

# ---- Module-level locks ------------------------------------------------------

# Prevents two simultaneous starts both seeing 0 active conversations
_start_lock = threading.Lock()

# Per-conversation locks — serializes continue/finalize on the same conversation
_conv_locks: dict[str, threading.Lock] = {}
_conv_locks_meta = threading.Lock()

# Per-conversation auto-finalize timers
_auto_timers: dict[str, threading.Timer] = {}
_auto_timers_meta = threading.Lock()


# ---- Lock helpers ------------------------------------------------------------


def _get_conv_lock(conversation_id: str) -> threading.Lock:
    with _conv_locks_meta:
        if conversation_id not in _conv_locks:
            _conv_locks[conversation_id] = threading.Lock()
        return _conv_locks[conversation_id]


# ---- Path helpers ------------------------------------------------------------


def _conversations_root() -> Path:
    return settings.conversations_dir


def _month_dir(dt: datetime | None = None) -> Path:
    dt = dt or datetime.now(UTC)
    return _conversations_root() / dt.strftime("%Y-%m")


def _vault_relative(abs_path: Path) -> str:
    try:
        return unicodedata.normalize("NFC", abs_path.relative_to(settings.vault).as_posix())
    except ValueError:
        return abs_path.as_posix()


def is_conversation_path(file_path: str) -> bool:
    """Return True if *file_path* is inside the conversations directory."""
    p = file_path.replace("\\", "/")
    return "/obsirag/conversations/" in p or p.startswith("obsirag/conversations/")


# ---- File I/O ----------------------------------------------------------------


def _find_note_path(conversation_id: str) -> Path | None:
    root = _conversations_root()
    if not root.exists():
        return None
    short_id = conversation_id[:8]
    for candidate in root.rglob(f"*{short_id}*.md"):
        try:
            post = fm_lib.loads(candidate.read_text(encoding="utf-8", errors="replace"))
            if post.get("conversation_id") == conversation_id:
                return candidate
        except Exception:
            continue
    return None


def _load(conversation_id: str) -> tuple[Path, fm_lib.Post] | tuple[None, None]:
    path = _find_note_path(conversation_id)
    if path is None:
        return None, None
    try:
        post = fm_lib.loads(path.read_text(encoding="utf-8", errors="replace"))
        return path, post
    except Exception:
        return None, None


def _save(path: Path, post: fm_lib.Post) -> None:
    path.write_text(fm_lib.dumps(post), encoding="utf-8")


# ---- Auto-finalize -----------------------------------------------------------


def _cancel_timer(conversation_id: str) -> None:
    with _auto_timers_meta:
        timer = _auto_timers.pop(conversation_id, None)
    if timer is not None:
        timer.cancel()


def _schedule_auto_finalize(conversation_id: str) -> None:
    _cancel_timer(conversation_id)

    def _auto_close() -> None:
        try:
            finalize_conversation(
                conversation_id=conversation_id,
                final_synthesis="[Auto-clôture : délai de 30 minutes dépassé sans activité]",
                resolved=False,
            )
        except Exception:
            pass

    timer = threading.Timer(AUTO_FINALIZE_SECONDS, _auto_close)
    timer.daemon = True
    with _auto_timers_meta:
        _auto_timers[conversation_id] = timer
    timer.start()


# ---- Active conversation count -----------------------------------------------


def _count_active() -> int:
    root = _conversations_root()
    if not root.exists():
        return 0
    count = 0
    for p in root.rglob("*.md"):
        try:
            post = fm_lib.loads(p.read_text(encoding="utf-8", errors="replace"))
            if post.get("type") == "conversation" and post.get("status") == "active":
                count += 1
        except Exception:
            continue
    return count


# ---- Stats -------------------------------------------------------------------


def get_conversation_stats() -> dict[str, Any]:
    """Compute conversation statistics from the vault directory (at-a-glance scan)."""
    root = _conversations_root()
    if not root.exists():
        return {
            "active_count": 0,
            "total_today": 0,
            "total_all_time": 0,
            "average_turns": 0.0,
            "resolution_rate": 0.0,
            "auto_finalized_count": 0,
        }

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    active_count = 0
    total_today = 0
    total_all_time = 0
    total_turns = 0
    resolved_count = 0
    closed_count = 0
    auto_finalized_count = 0

    for p in root.rglob("*.md"):
        try:
            post = fm_lib.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if post.get("type") != "conversation":
            continue

        total_all_time += 1
        status = post.get("status", "")
        created_at = str(post.get("created_at") or "")

        if created_at.startswith(today):
            total_today += 1

        if status == "active":
            active_count += 1
        elif status == "closed":
            closed_count += 1
            if post.get("resolved") is True:
                resolved_count += 1
            synthesis = post.content if hasattr(post, "content") else ""
            if "Auto-clôture" in synthesis or "Auto-clôture" in str(post.get("trigger_explanation", "")):
                auto_finalized_count += 1

        total_turns += int(post.get("turns_count") or 0)

    avg_turns = (total_turns / total_all_time) if total_all_time else 0.0
    resolution_rate = (resolved_count / closed_count) if closed_count else 0.0

    return {
        "active_count": active_count,
        "total_today": total_today,
        "total_all_time": total_all_time,
        "average_turns": round(avg_turns, 2),
        "resolution_rate": round(resolution_rate, 2),
        "auto_finalized_count": auto_finalized_count,
    }


# ---- Note content builder ----------------------------------------------------


def _fmt_sources(sources: list) -> str:
    lines = []
    for s in sources:
        if isinstance(s, dict):
            title = s.get("noteTitle") or s.get("filePath") or ""
            score = s.get("score")
            if score is not None:
                lines.append(f"- {title} (score {score:.2f})")
            elif title:
                lines.append(f"- {title}")
    return "\n".join(lines) if lines else "_(aucune source)_"


def _build_initial_body(
    *,
    title: str,
    triggering_question: str,
    trigger_reason: str,
    trigger_explanation: str,
    initial_answer: str,
    initial_sources: list,
    first_followup_question: str,
    turn_ts: str,
    first_answer: str,
    first_sources: list,
) -> str:
    lines = [
        f"# Investigation : {title}",
        "",
        "## Question initiale (utilisateur)",
        f"> {triggering_question}",
        "",
        "## Déclencheur",
        f"**Type :** {trigger_reason}",
        f"**Justification :** {trigger_explanation}",
        "",
        "### Réponse RAG initiale",
        initial_answer or "_(pas de réponse)_",
        "",
        "**Sources consultées :**",
        _fmt_sources(initial_sources),
        "",
        "---",
        "",
        f"## Tour 1 — {turn_ts}",
        "**Raisonnement :** _(démarrage de l'investigation)_",
        f"**Question :** {first_followup_question}",
        "",
        f"**Réponse :** {first_answer}",
        "",
        "**Sources :**",
        _fmt_sources(first_sources),
    ]
    return "\n".join(lines)


def _append_turn_to_body(body: str, *, turn_n: int, turn_ts: str, question: str, reasoning: str, answer: str, sources: list) -> str:
    turn_block = "\n".join([
        "",
        f"## Tour {turn_n} — {turn_ts}",
        f"**Raisonnement :** {reasoning}",
        f"**Question :** {question}",
        "",
        f"**Réponse :** {answer}",
        "",
        "**Sources :**",
        _fmt_sources(sources),
    ])
    return body + turn_block


def _append_synthesis_to_body(body: str, *, final_synthesis: str, resolved: bool) -> str:
    resolved_str = "✅ oui" if resolved else "❌ non"
    block = "\n".join([
        "",
        "---",
        "",
        "## Synthèse finale",
        "",
        final_synthesis,
        "",
        f"**Résolu :** {resolved_str}",
    ])
    return body + block


def _aggregate_sources(existing: list[str], new_sources: list) -> list[str]:
    paths = list(existing)
    seen = set(paths)
    for s in new_sources:
        if isinstance(s, dict):
            fp = s.get("filePath") or s.get("file_path") or ""
            if fp and fp not in seen:
                paths.append(fp)
                seen.add(fp)
    return paths


# ---- Public API --------------------------------------------------------------


def start_conversation(
    title: str,
    triggering_question: str,
    trigger_reason: str,
    trigger_explanation: str,
    initial_rag_response: dict,
    first_followup_question: str,
) -> dict[str, Any]:
    # ---- Validate inputs ----
    if trigger_reason not in VALID_TRIGGER_REASONS:
        raise ValueError(
            f"trigger_reason invalide : '{trigger_reason}'. "
            f"Valeurs acceptées : {sorted(VALID_TRIGGER_REASONS)}"
        )
    if len(trigger_explanation) > MAX_TRIGGER_EXPLANATION:
        raise ValueError(
            f"trigger_explanation trop long ({len(trigger_explanation)} chars, max {MAX_TRIGGER_EXPLANATION})"
        )
    if not title.strip():
        raise ValueError("title must not be empty")
    if not triggering_question.strip():
        raise ValueError("triggering_question must not be empty")
    if not first_followup_question.strip():
        raise ValueError("first_followup_question must not be empty")

    with _start_lock:
        active_count = _count_active()
        if active_count >= 1:
            raise RuntimeError(
                "409: Une conversation est déjà active. "
                "Clôturez-la avec obsirag_conversation_finalize avant d'en démarrer une nouvelle."
            )

        # ---- Generate IDs and paths ----
        conversation_id = uuid.uuid4().hex
        slug = build_ascii_stem(title, max_length=50, separator="-")
        short_id = conversation_id[:8]

        now = datetime.now(UTC)
        month_dir = _month_dir(now)
        month_dir.mkdir(parents=True, exist_ok=True)
        note_path = month_dir / f"{slug}-{short_id}.md"

        # ---- Call RAG for first follow-up ----
        from src.mcp.runtime import ask_rag_payload  # local import to avoid circular at module load
        rag_result = ask_rag_payload(first_followup_question)
        first_answer = str(rag_result.get("answer", ""))[:MAX_ANSWER_LEN]
        first_sources: list = rag_result.get("sources", [])
        provider: str = rag_result.get("provider", "ollama")
        sentinel: bool = bool(rag_result.get("sentinel", False))

        # ---- Build initial content ----
        initial_sources: list = (
            initial_rag_response.get("sources", [])
            if isinstance(initial_rag_response, dict)
            else []
        )
        initial_answer: str = (
            str(initial_rag_response.get("answer", ""))
            if isinstance(initial_rag_response, dict)
            else str(initial_rag_response)
        )
        turn_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        body = _build_initial_body(
            title=title,
            triggering_question=triggering_question,
            trigger_reason=trigger_reason,
            trigger_explanation=trigger_explanation,
            initial_answer=initial_answer,
            initial_sources=initial_sources,
            first_followup_question=first_followup_question,
            turn_ts=turn_ts,
            first_answer=first_answer,
            first_sources=first_sources,
        )

        sources_consulted = _aggregate_sources(
            _aggregate_sources([], initial_sources),
            first_sources,
        )

        post = fm_lib.Post(
            body,
            **{
                "type": "conversation",
                "status": "active",
                "created_at": now.isoformat().replace("+00:00", "Z"),
                "closed_at": None,
                "participant": "claude",
                "trigger_reason": trigger_reason,
                "trigger_explanation": trigger_explanation[:MAX_TRIGGER_EXPLANATION],
                "turns_count": 1,
                "turns_remaining": MAX_TURNS,
                "resolved": None,
                "exclude_from_rag": True,
                "conversation_id": conversation_id,
                "tags": ["claude-investigation"],
                "sources_consulted": sources_consulted,
                "turns_history": [
                    {"role": "user", "content": first_followup_question},
                    {"role": "assistant", "content": first_answer[:600]},
                ],
            },
        )
        _save(note_path, post)

    _schedule_auto_finalize(conversation_id)

    return {
        "conversation_id": conversation_id,
        "note_path": _vault_relative(note_path),
        "answer": first_answer,
        "sources": first_sources,
        "provider": provider,
        "sentinel": sentinel,
        "turns_remaining": MAX_TURNS,
    }


def continue_conversation(
    conversation_id: str,
    question: str,
    reasoning: str,
) -> dict[str, Any]:
    if len(reasoning) > MAX_REASONING:
        raise ValueError(
            f"reasoning trop long ({len(reasoning)} chars, max {MAX_REASONING})"
        )
    if not question.strip():
        raise ValueError("question must not be empty")

    lock = _get_conv_lock(conversation_id)
    with lock:
        path, post = _load(conversation_id)
        if path is None:
            raise LookupError(f"404: Conversation {conversation_id!r} introuvable")

        status = post.get("status", "")
        if status == "closed":
            raise RuntimeError(f"409: Conversation {conversation_id!r} déjà clôturée")

        turns_remaining = int(post.get("turns_remaining") or 0)
        if turns_remaining <= 0:
            raise RuntimeError(
                f"429: Limite de tours atteinte. "
                "Appelez obsirag_conversation_finalize pour clôturer la conversation."
            )

        # ---- Call RAG with conversation history for contextual continuity ----
        from src.mcp.runtime import ask_rag_payload
        turns_history: list = list(post.get("turns_history") or [])
        rag_result = ask_rag_payload(question, history=turns_history or None)
        answer = str(rag_result.get("answer", ""))[:MAX_ANSWER_LEN]
        sources: list = rag_result.get("sources", [])
        provider: str = rag_result.get("provider", "ollama")
        sentinel: bool = bool(rag_result.get("sentinel", False))

        # ---- Update note ----
        turns_count = int(post.get("turns_count") or 0) + 1
        turns_remaining -= 1
        turn_ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_body = _append_turn_to_body(
            post.content,
            turn_n=turns_count,
            turn_ts=turn_ts,
            question=question,
            reasoning=reasoning,
            answer=answer,
            sources=sources,
        )

        turns_history.append({"role": "user", "content": question})
        turns_history.append({"role": "assistant", "content": answer[:600]})

        post["turns_count"] = turns_count
        post["turns_remaining"] = turns_remaining
        post["sources_consulted"] = _aggregate_sources(
            list(post.get("sources_consulted") or []),
            sources,
        )
        post["turns_history"] = turns_history[-6:]  # 3 derniers tours max
        post.content = new_body
        _save(path, post)

    # Reset the auto-finalize timer on each continue
    _schedule_auto_finalize(conversation_id)

    return {
        "conversation_id": conversation_id,
        "note_path": _vault_relative(path),
        "answer": answer,
        "sources": sources,
        "provider": provider,
        "sentinel": sentinel,
        "turns_remaining": turns_remaining,
    }


def finalize_conversation(
    conversation_id: str,
    final_synthesis: str,
    resolved: bool,
) -> dict[str, Any]:
    _cancel_timer(conversation_id)

    lock = _get_conv_lock(conversation_id)
    with lock:
        path, post = _load(conversation_id)
        if path is None:
            raise LookupError(f"404: Conversation {conversation_id!r} introuvable")

        if post.get("status") == "closed":
            raise RuntimeError(f"409: Conversation {conversation_id!r} déjà clôturée")

        now = datetime.now(UTC)
        closed_at = now.isoformat().replace("+00:00", "Z")

        created_at_raw = str(post.get("created_at") or "")
        try:
            created_at_dt = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
            duration_seconds = int((now - created_at_dt).total_seconds())
        except Exception:
            duration_seconds = 0

        new_body = _append_synthesis_to_body(
            post.content,
            final_synthesis=final_synthesis,
            resolved=resolved,
        )

        post["status"] = "closed"
        post["closed_at"] = closed_at
        post["resolved"] = resolved
        post.content = new_body
        _save(path, post)

        turns_count = int(post.get("turns_count") or 0)

    return {
        "conversation_id": conversation_id,
        "note_path": _vault_relative(path),
        "status": "closed",
        "turns_count": turns_count,
        "duration_seconds": duration_seconds,
    }
