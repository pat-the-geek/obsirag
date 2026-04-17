from __future__ import annotations

from pathlib import Path

from src.api import chat_fallback_worker as worker


def test_extract_focus_query_strips_chatty_prefix() -> None:
    assert worker._extract_focus_query("Parle-moi d'Artemis II") == "Artemis II"


def test_tokenize_query_keeps_relevant_subject_terms() -> None:
    assert worker._tokenize_query("Artemis II") == ["artemis", "ii"]


def test_generated_chat_artifacts_are_excluded() -> None:
    assert worker._is_generated_chat_artifact("obsirag/insights/2026-04/chat_parle_moi_de_artemis.md") is True
    assert worker._is_generated_chat_artifact("obsirag/web_insights/web_artemis.md") is False


def test_rank_note_favors_relevant_web_insight() -> None:
    record = worker._NoteRecord(
        path=Path("/tmp/web_artemis.md"),
        rel_path="obsirag/web_insights/web_artemis.md",
        title="Artemis II",
        body="Mission Artemis II autour de la Lune.",
        date_modified="2026-04-17T00:00:00",
        note_type="web_insight",
    )
    score, coverage, exact_hits = worker._rank_note(record, ["artemis", "ii"], "artemis ii")
    assert score > 0
    assert coverage >= 2
    assert exact_hits >= 1