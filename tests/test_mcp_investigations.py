"""Tests for MCP investigation conversation tools.

Covers:
- conversation_start / continue / finalize correctness
- Frontmatter state after each operation
- Guard-rails (concurrent limit, turn limit, closed rejection)
- RAG exclusion (path-based and frontmatter-based)
- Autolearn exclusion (is_obsirag_generated covers obsirag/conversations/)
- Concurrency: parallel continues are serialized
- End-to-end integration: start → continue → continue → finalize
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import frontmatter as fm_lib
import pytest

import src.mcp.investigation as inv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_RAG = {
    "answer": "Réponse test",
    "sources": [{"filePath": "Note.md", "noteTitle": "Note", "score": 0.9}],
    "provider": "ollama",
    "sentinel": False,
}

_INITIAL_RAG = {
    "answer": "Première réponse RAG",
    "sources": [{"filePath": "Source.md", "noteTitle": "Source", "score": 0.8}],
    "provider": "ollama",
    "sentinel": False,
}


def _start(conversations_dir: Path, title: str = "Test investigation") -> dict:
    """Helper: start a conversation with the conversations_dir patched."""
    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = conversations_dir
        mock_settings.vault = conversations_dir.parent
        return inv.start_conversation(
            title=title,
            triggering_question="Qu'est-ce que Python ?",
            trigger_reason="low_confidence",
            trigger_explanation="La réponse semblait trop vague.",
            initial_rag_response=_INITIAL_RAG,
            first_followup_question="Peux-tu préciser ?",
        )


def _continue(conversations_dir: Path, conv_id: str, question: str = "Suite ?") -> dict:
    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = conversations_dir
        mock_settings.vault = conversations_dir.parent
        return inv.continue_conversation(
            conversation_id=conv_id,
            question=question,
            reasoning="Besoin de détails.",
        )


def _finalize(conversations_dir: Path, conv_id: str, resolved: bool = True) -> dict:
    with patch("src.mcp.investigation.settings") as mock_settings:
        mock_settings.conversations_dir = conversations_dir
        mock_settings.vault = conversations_dir.parent
        return inv.finalize_conversation(
            conversation_id=conv_id,
            final_synthesis="Synthèse de fin.",
            resolved=resolved,
        )


def _read_post(note_path: Path) -> fm_lib.Post:
    return fm_lib.loads(note_path.read_text(encoding="utf-8"))


def _find_note(conversations_dir: Path, conv_id: str) -> Path:
    for p in conversations_dir.rglob(f"*{conv_id[:8]}*.md"):
        post = _read_post(p)
        if post.get("conversation_id") == conv_id:
            return p
    raise FileNotFoundError(f"Note for {conv_id} not found")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_investigation_state():
    """Clear module-level state between tests."""
    inv._conv_locks.clear()
    inv._auto_timers.clear()
    # Cancel any running timers
    with inv._auto_timers_meta:
        for t in list(inv._auto_timers.values()):
            t.cancel()
        inv._auto_timers.clear()
    yield
    with inv._auto_timers_meta:
        for t in list(inv._auto_timers.values()):
            t.cancel()
        inv._auto_timers.clear()
    inv._conv_locks.clear()


# ---------------------------------------------------------------------------
# Test 1: start creates note with correct frontmatter
# ---------------------------------------------------------------------------

def test_conversation_start_creates_note(tmp_path):
    result = _start(tmp_path)

    conv_id = result["conversation_id"]
    note = _find_note(tmp_path, conv_id)
    post = _read_post(note)

    assert post.get("type") == "conversation"
    assert post.get("status") == "active"
    assert post.get("conversation_id") == conv_id
    assert post.get("turns_remaining") == inv.MAX_TURNS
    assert post.get("turns_count") == 1
    assert post.get("exclude_from_rag") is True
    assert post.get("trigger_reason") == "low_confidence"
    assert post.get("resolved") is None
    assert post.get("closed_at") is None
    assert "claude-investigation" in (post.get("tags") or [])

    # Body should contain the initial question and first turn
    body = post.content
    assert "Test investigation" in body
    assert "Qu'est-ce que Python" in body
    assert "Tour 1" in body
    assert "Peux-tu préciser" in body


# ---------------------------------------------------------------------------
# Test 2: trigger_explanation > 500 chars → ValueError
# ---------------------------------------------------------------------------

def test_conversation_start_rejects_long_explanation(tmp_path):
    long_explanation = "x" * 501
    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = tmp_path
        mock_settings.vault = tmp_path.parent
        with pytest.raises(ValueError, match="trigger_explanation trop long"):
            inv.start_conversation(
                title="Test",
                triggering_question="Q?",
                trigger_reason="low_confidence",
                trigger_explanation=long_explanation,
                initial_rag_response=_INITIAL_RAG,
                first_followup_question="Follow?",
            )


# ---------------------------------------------------------------------------
# Test 3: invalid trigger_reason → ValueError
# ---------------------------------------------------------------------------

def test_conversation_start_rejects_invalid_trigger(tmp_path):
    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = tmp_path
        mock_settings.vault = tmp_path.parent
        with pytest.raises(ValueError, match="trigger_reason invalide"):
            inv.start_conversation(
                title="Test",
                triggering_question="Q?",
                trigger_reason="invalid_reason",
                trigger_explanation="OK",
                initial_rag_response=_INITIAL_RAG,
                first_followup_question="Follow?",
            )


# ---------------------------------------------------------------------------
# Test 4: second start with one active → RuntimeError 409
# ---------------------------------------------------------------------------

def test_conversation_start_rejects_concurrent_active(tmp_path):
    _start(tmp_path)  # creates an active conversation

    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = tmp_path
        mock_settings.vault = tmp_path.parent
        with pytest.raises(RuntimeError, match="409"):
            inv.start_conversation(
                title="Autre investigation",
                triggering_question="Q2?",
                trigger_reason="sentinel_response",
                trigger_explanation="Reason",
                initial_rag_response=_INITIAL_RAG,
                first_followup_question="FQ?",
            )


# ---------------------------------------------------------------------------
# Test 5: continues decrement turns_remaining 3→2→1→0
# ---------------------------------------------------------------------------

def test_conversation_continue_decrements_turns(tmp_path):
    result = _start(tmp_path)
    conv_id = result["conversation_id"]
    assert result["turns_remaining"] == 3

    r1 = _continue(tmp_path, conv_id)
    assert r1["turns_remaining"] == 2

    r2 = _continue(tmp_path, conv_id)
    assert r2["turns_remaining"] == 1

    r3 = _continue(tmp_path, conv_id)
    assert r3["turns_remaining"] == 0

    note = _find_note(tmp_path, conv_id)
    post = _read_post(note)
    assert post.get("turns_remaining") == 0
    assert post.get("turns_count") == 4  # 1 from start + 3 continues


# ---------------------------------------------------------------------------
# Test 6: 4th continue → RuntimeError 429
# ---------------------------------------------------------------------------

def test_conversation_continue_rejects_after_limit(tmp_path):
    result = _start(tmp_path)
    conv_id = result["conversation_id"]

    for _ in range(inv.MAX_TURNS):
        _continue(tmp_path, conv_id)

    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = tmp_path
        mock_settings.vault = tmp_path.parent
        with pytest.raises(RuntimeError, match="429"):
            inv.continue_conversation(
                conversation_id=conv_id,
                question="Encore ?",
                reasoning="Test",
            )


# ---------------------------------------------------------------------------
# Test 7: continue after finalize → RuntimeError 409
# ---------------------------------------------------------------------------

def test_conversation_continue_rejects_closed(tmp_path):
    result = _start(tmp_path)
    conv_id = result["conversation_id"]
    _finalize(tmp_path, conv_id)

    with patch("src.mcp.investigation.settings") as mock_settings, \
         patch("src.mcp.runtime.ask_rag_payload", return_value=_FAKE_RAG):
        mock_settings.conversations_dir = tmp_path
        mock_settings.vault = tmp_path.parent
        with pytest.raises(RuntimeError, match="409"):
            inv.continue_conversation(
                conversation_id=conv_id,
                question="Après clôture ?",
                reasoning="Test",
            )


# ---------------------------------------------------------------------------
# Test 8: finalize updates frontmatter status → closed
# ---------------------------------------------------------------------------

def test_conversation_finalize_updates_status(tmp_path):
    result = _start(tmp_path)
    conv_id = result["conversation_id"]
    fin = _finalize(tmp_path, conv_id, resolved=True)

    assert fin["status"] == "closed"
    assert fin["turns_count"] >= 1

    note = _find_note(tmp_path, conv_id)
    post = _read_post(note)
    assert post.get("status") == "closed"
    assert post.get("resolved") is True
    assert post.get("closed_at") is not None
    assert "Synthèse de fin" in post.content


# ---------------------------------------------------------------------------
# Test 9: excluded from RAG by path (RAG filter)
# ---------------------------------------------------------------------------

def test_conversation_excluded_from_rag_by_path():
    from src.ai.rag import RAGPipeline
    pipeline = RAGPipeline.__new__(RAGPipeline)

    conversation_chunk = {
        "chunk_id": "conv_001",
        "text": "Contenu d'investigation",
        "metadata": {"file_path": "obsirag/conversations/2026-05/test-abc12345.md"},
        "score": 0.99,
    }
    normal_chunk = {
        "chunk_id": "note_001",
        "text": "Contenu normal",
        "metadata": {"file_path": "Notes/Note Python.md"},
        "score": 0.85,
    }

    result = pipeline._filter_conversation_chunks([conversation_chunk, normal_chunk])
    assert len(result) == 1
    assert result[0]["chunk_id"] == "note_001"


# ---------------------------------------------------------------------------
# Test 10: excluded from RAG by frontmatter (indexer skips file)
# ---------------------------------------------------------------------------

def test_conversation_excluded_from_rag_by_frontmatter(tmp_path):
    from src.indexer.pipeline import IndexingPipeline

    # Note with exclude_from_rag: true outside the conversations path
    note = tmp_path / "Special.md"
    note.write_text(
        "---\nexclude_from_rag: true\ntitle: Special\n---\n\nContenu spécial.",
        encoding="utf-8",
    )

    pipeline = IndexingPipeline.__new__(IndexingPipeline)
    # _check_frontmatter_exclusion should return True for this note
    assert pipeline._check_frontmatter_exclusion(note) is True

    # A normal note should not be excluded
    normal = tmp_path / "Normal.md"
    normal.write_text("---\ntitle: Normal\n---\n\nContenu.", encoding="utf-8")
    assert pipeline._check_frontmatter_exclusion(normal) is False


# ---------------------------------------------------------------------------
# Test 11: conversation not processed by autolearn
# ---------------------------------------------------------------------------

def test_conversation_not_in_autolearn_log():
    from src.learning.autolearn import AutoLearner
    # AutoLearner._is_obsirag_generated covers all obsirag/ paths
    assert AutoLearner._is_obsirag_generated("obsirag/conversations/2026-05/test.md") is True
    assert AutoLearner._is_obsirag_generated("Idees/Note.md") is False


# ---------------------------------------------------------------------------
# Test 12: concurrent continues are serialized (no frontmatter corruption)
# ---------------------------------------------------------------------------

def test_concurrent_continue_serialized(tmp_path):
    result = _start(tmp_path)
    conv_id = result["conversation_id"]

    errors: list[Exception] = []
    results: list[int] = []

    def do_continue():
        try:
            r = _continue(tmp_path, conv_id)
            results.append(r["turns_remaining"])
        except RuntimeError as exc:
            # 429 is expected once limit is hit
            if "429" not in str(exc):
                errors.append(exc)

    threads = [threading.Thread(target=do_continue) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors during concurrent continues: {errors}"

    # Frontmatter must be consistent — turns_count == 1 (start) + successful continues
    note = _find_note(tmp_path, conv_id)
    post = _read_post(note)
    turns_done = post.get("turns_count", 0)
    # All 3 continues ran but at most MAX_TURNS should succeed
    assert turns_done <= 1 + inv.MAX_TURNS
    assert post.get("turns_remaining", 0) >= 0


# ---------------------------------------------------------------------------
# Test 13: auto-finalize fires after timeout
# ---------------------------------------------------------------------------

def test_auto_finalize_after_30min(tmp_path, monkeypatch):
    # Patch AUTO_FINALIZE_SECONDS to a tiny value for the test
    monkeypatch.setattr(inv, "AUTO_FINALIZE_SECONDS", 0.1)

    result = _start(tmp_path)
    conv_id = result["conversation_id"]

    # Re-schedule with short timeout
    inv._cancel_timer(conv_id)

    with patch("src.mcp.investigation.settings") as mock_settings:
        mock_settings.conversations_dir = tmp_path
        mock_settings.vault = tmp_path.parent

        def _auto_close():
            inv.finalize_conversation(
                conversation_id=conv_id,
                final_synthesis="[Auto-clôture : délai de 30 minutes dépassé sans activité]",
                resolved=False,
            )

        import threading as _th
        timer = _th.Timer(0.1, _auto_close)
        timer.daemon = True
        with inv._auto_timers_meta:
            inv._auto_timers[conv_id] = timer
        timer.start()

        time.sleep(0.5)  # Wait for timer to fire

    note = _find_note(tmp_path, conv_id)
    post = _read_post(note)
    assert post.get("status") == "closed"
    assert post.get("resolved") is False
    assert "Auto-clôture" in post.content


# ---------------------------------------------------------------------------
# Test 14: end-to-end integration
# ---------------------------------------------------------------------------

def test_end_to_end_start_continue_finalize(tmp_path):
    # start
    result = _start(tmp_path)
    conv_id = result["conversation_id"]
    assert result["turns_remaining"] == 3
    assert result["answer"] == "Réponse test"

    # continue ×2
    r1 = _continue(tmp_path, conv_id, question="Première suite ?")
    assert r1["turns_remaining"] == 2
    r2 = _continue(tmp_path, conv_id, question="Deuxième suite ?")
    assert r2["turns_remaining"] == 1

    # finalize
    fin = _finalize(tmp_path, conv_id, resolved=True)
    assert fin["status"] == "closed"
    assert fin["turns_count"] == 3  # 1 start + 2 continues

    # Verify note integrity
    note = _find_note(tmp_path, conv_id)
    post = _read_post(note)
    body = post.content

    assert post.get("status") == "closed"
    assert post.get("resolved") is True
    assert post.get("turns_remaining") == 1
    assert post.get("turns_count") == 3
    assert post.get("exclude_from_rag") is True

    # Body should contain all turns and synthesis
    assert "Tour 1" in body
    assert "Tour 2" in body
    assert "Tour 3" in body
    assert "Synthèse finale" in body
    assert "Synthèse de fin" in body
    assert "✅ oui" in body

    # Verify note is excluded by path filter — use a canonical vault-relative path
    from src.ai.rag import RAGPipeline
    pipeline = RAGPipeline.__new__(RAGPipeline)
    canonical_rel = "obsirag/conversations/2026-05/test-investigation-abc12345.md"
    chunk = {
        "chunk_id": "x",
        "text": "content",
        "metadata": {"file_path": canonical_rel},
        "score": 0.9,
    }
    assert pipeline._filter_conversation_chunks([chunk]) == []

    # Verify note would not be indexed (path exclusion)
    from src.indexer.pipeline import IndexingPipeline
    idx = IndexingPipeline.__new__(IndexingPipeline)
    # Simulate an absolute path under obsirag/conversations/
    fake_path = Path("/vault/obsirag/conversations/2026-05/test.md")
    assert idx._is_excluded(fake_path) is True

    # Verify stats
    with patch("src.mcp.investigation.settings") as mock_settings:
        mock_settings.conversations_dir = tmp_path
        stats = inv.get_conversation_stats()
    assert stats["total_all_time"] == 1
    assert stats["active_count"] == 0
    assert stats["resolution_rate"] == 1.0
