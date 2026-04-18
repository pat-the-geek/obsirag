from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.api import chat_fallback_worker as worker


def test_extract_focus_query_strips_chatty_prefix() -> None:
    assert worker._extract_focus_query("Parle-moi d'Artemis II") == "Artemis II"
    assert worker._extract_focus_query("   ???   ") == "???"


def test_tokenize_query_keeps_relevant_subject_terms() -> None:
    assert worker._tokenize_query("Artemis II") == ["artemis", "ii"]
    assert worker._tokenize_query("de de io ii ii") == ["ii"]


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


def test_note_type_for_path_recognizes_generated_buckets() -> None:
    assert worker._note_type_for_path("obsirag/web_insights/x.md") == "web_insight"
    assert worker._note_type_for_path("obsirag/insights/x.md") == "insight"
    assert worker._note_type_for_path("obsirag/synapses/x.md") == "synapse"
    assert worker._note_type_for_path("obsirag/synthesis/x.md") == "report"
    assert worker._note_type_for_path("Notes/x.md") == "user"


def test_parse_note_reads_frontmatter_and_falls_back_on_errors(tmp_path: Path) -> None:
    note = tmp_path / "Ada.md"
    note.write_text("---\ntitle: Ada Lovelace\n---\n\nPionniere.", encoding="utf-8")
    title, body = worker._parse_note(note)
    assert title == "Ada Lovelace"
    assert body == "Pionniere."

    broken = tmp_path / "Broken.md"
    broken.write_text("not really frontmatter", encoding="utf-8")
    with patch("src.api.chat_fallback_worker.frontmatter.loads", side_effect=RuntimeError("boom")):
        title, body = worker._parse_note(broken)
    assert title == "Broken"
    assert body == "not really frontmatter"

    empty = tmp_path / "Empty.md"
    empty.write_text("   ", encoding="utf-8")
    title, body = worker._parse_note(empty)
    assert title == "Empty"
    assert body == ""


def test_iter_note_records_filters_hidden_generated_large_and_empty_notes(tmp_settings) -> None:
    vault = tmp_settings.vault
    vault.mkdir(parents=True, exist_ok=True)
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "Ignored.md").write_text("ignored", encoding="utf-8")
    (vault / "obsirag" / "insights" / "2026-04").mkdir(parents=True)
    (vault / "obsirag" / "insights" / "2026-04" / "chat_test.md").write_text("generated", encoding="utf-8")
    (vault / "empty.md").write_text("   ", encoding="utf-8")
    keep = vault / "Notes" / "Ada.md"
    keep.parent.mkdir(parents=True)
    keep.write_text("---\ntitle: Ada Lovelace\n---\n\nPionniere.", encoding="utf-8")

    oversized = vault / "too-large.md"
    oversized.write_text("large", encoding="utf-8")

    original_stat = Path.stat

    def _stat(path: Path, *args, **kwargs):
        result = original_stat(path)
        if path == oversized:
            return type("_Stat", (), {"st_size": tmp_settings.max_note_size_bytes + 1, "st_mtime": result.st_mtime})()
        return result

    with (
        patch("src.api.chat_fallback_worker.settings", tmp_settings),
        patch("pathlib.Path.stat", autospec=True, side_effect=_stat),
    ):
        records = worker._iter_note_records()

    assert [record.rel_path for record in records] == ["Notes/Ada.md"]
    assert records[0].title == "Ada Lovelace"


def test_iter_note_records_returns_empty_for_missing_vault_and_stat_errors(tmp_settings) -> None:
    with patch("src.api.chat_fallback_worker.settings", tmp_settings.model_copy(update={"vault_path": str(tmp_settings.vault / "missing")})):
        assert worker._iter_note_records() == []

    vault = tmp_settings.vault
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "Ada.md"
    note.write_text("Ada", encoding="utf-8")

    original_stat = Path.stat

    def _stat_fail(path: Path, *args, **kwargs):
        if path == note:
            raise OSError("stat failed")
        return original_stat(path)

    with (
        patch("src.api.chat_fallback_worker.settings", tmp_settings),
        patch("pathlib.Path.stat", autospec=True, side_effect=_stat_fail),
    ):
        records = worker._iter_note_records()

    assert len(records) == 1
    assert records[0].date_modified == ""


def test_select_excerpt_uses_ranked_paragraphs_or_first_fallback() -> None:
    body = "Alpha detail.\n\nAda Lovelace invente quelque chose.\n\nEncore Ada Lovelace et calcul."
    excerpt = worker._select_excerpt(body, ["ada", "lovelace"], "ada lovelace", max_chars=80)
    assert "Ada Lovelace" in excerpt

    fallback = worker._select_excerpt("Paragraphe neutre.\n\nAutre bloc.", ["zzz"], "zzz", max_chars=20)
    assert fallback == "Paragraphe neutre."
    assert worker._select_excerpt("   ", ["ada"], "ada") == ""

    truncated = worker._select_excerpt(
        "Ada Lovelace invente quelque chose de tres long.\n\nAda Lovelace encore.",
        ["ada", "lovelace"],
        "ada lovelace",
        max_chars=10,
    )
    assert truncated.endswith("…")


def test_record_to_chunk_builds_metadata_and_returns_none_for_empty_excerpt() -> None:
    record = worker._NoteRecord(
        path=Path("/tmp/Ada.md"),
        rel_path="People/Ada.md",
        title="Ada Lovelace",
        body="Ada Lovelace pionniere.",
        date_modified="2026-04-18T10:00:00",
        note_type="user",
    )

    chunk = worker._record_to_chunk(record, "Qui est Ada Lovelace ?", is_primary=True)
    assert chunk is not None
    assert chunk["metadata"]["is_primary"] is True
    assert chunk["metadata"]["file_path"] == "People/Ada.md"

    with patch("src.api.chat_fallback_worker._select_excerpt", return_value=""):
        assert worker._record_to_chunk(record, "Qui est Ada Lovelace ?", is_primary=False) is None


def test_fallback_chroma_search_and_lookup_helpers() -> None:
    records = [
        worker._NoteRecord(
            path=Path("/tmp/Ada.md"),
            rel_path="People/Ada.md",
            title="Ada Lovelace",
            body="Ada Lovelace mathematician.",
            date_modified="2026-04-18T10:00:00",
            note_type="user",
        ),
        worker._NoteRecord(
            path=Path("/tmp/Other.md"),
            rel_path="People/Other.md",
            title="Other",
            body="Completely unrelated.",
            date_modified="2026-04-17T10:00:00",
            note_type="insight",
        ),
    ]
    chroma = worker._FallbackChroma(records)

    results = chroma.search("Ada Lovelace", top_k=2)
    assert len(results) == 1
    assert results[0]["metadata"]["is_primary"] is True

    by_title = chroma.get_chunks_by_note_title("Ada Lovelace", limit=1)
    assert len(by_title) == 1

    by_path = chroma.get_chunks_by_file_path("People/Ada.md", limit=1)
    assert len(by_path) == 1

    multi = chroma.get_chunks_by_file_paths(["People/Ada.md"], limit_per_path=1)
    assert list(multi) == ["People/Ada.md"]


def test_fallback_chroma_filters_with_eq_dict_and_skips_non_positive_scores() -> None:
    records = [
        worker._NoteRecord(
            path=Path("/tmp/Ada.md"),
            rel_path="People/Ada.md",
            title="Ada Lovelace",
            body="Ada Lovelace mathematician.",
            date_modified="2026-04-18T10:00:00",
            note_type="report",
        )
    ]
    chroma = worker._FallbackChroma(records)

    filtered = chroma._filter_records({"file_path": {"$eq": "People/Ada.md"}})
    assert len(filtered) == 1

    with patch("src.api.chat_fallback_worker._rank_note", return_value=(0, 0, 0)):
        assert chroma.search("question", top_k=1) == []

    short_record = worker._NoteRecord(
        path=Path("/tmp/X.md"),
        rel_path="Notes/X.md",
        title="X",
        body="x x x",
        date_modified="2026-04-18T10:00:00",
        note_type="user",
    )
    short_chroma = worker._FallbackChroma([short_record])
    short_results = short_chroma.search("x", top_k=1)
    assert len(short_results) == 1


def test_path_bias_covers_all_known_and_unknown_types() -> None:
    for note_type, expected in {
        "user": 10,
        "web_insight": 7,
        "report": 3,
        "synapse": 1,
        "insight": -2,
        "unknown": 0,
    }.items():
        record = worker._NoteRecord(Path("/tmp/x.md"), "x.md", "x", "body", "", note_type)
        assert worker._path_bias(record) == expected


def test_build_runtime_wires_fallback_chroma(tmp_settings) -> None:
    metrics = MagicMock()
    llm = MagicMock()
    rag = MagicMock()
    records = []
    with (
        patch("src.api.chat_fallback_worker.settings", tmp_settings),
        patch("src.api.chat_fallback_worker.configure_logging") as configure,
        patch("src.api.chat_fallback_worker.MetricsRecorder", return_value=metrics),
        patch("src.api.chat_fallback_worker.MlxClient", return_value=llm),
        patch("src.api.chat_fallback_worker.RAGPipeline", return_value=rag) as rag_cls,
    ):
        built_llm, built_rag = worker._build_runtime(records)

    configure.assert_called_once_with(tmp_settings.log_level, tmp_settings.log_dir)
    assert isinstance(rag_cls.call_args.args[0], worker._FallbackChroma)
    assert built_llm is llm
    assert built_rag is rag


def test_main_requires_prompt() -> None:
    with patch("src.api.chat_fallback_worker.json.load", return_value={"prompt": "   "}):
        with pytest.raises(SystemExit, match="Missing prompt"):
            worker.main()


def test_main_returns_filesystem_sentinel_when_no_chunks() -> None:
    llm = MagicMock()
    rag = MagicMock()
    rag._resolve_query_with_history.return_value = "Ada Lovelace"
    rag._chroma.search.return_value = []
    with (
        patch("src.api.chat_fallback_worker.json.load", return_value={"prompt": "Ada", "history": []}),
        patch("src.api.chat_fallback_worker._iter_note_records", return_value=[]),
        patch("src.api.chat_fallback_worker._build_runtime", return_value=(llm, rag)),
        patch("src.api.chat_fallback_worker.sys.stdout", new=io.StringIO()) as stdout,
    ):
        code = worker.main()

    assert code == 0
    assert '"fallbackMode": "filesystem"' in stdout.getvalue()
    assert llm.load.call_count == 0
    llm.unload.assert_called_once_with()


def test_main_builds_answer_from_ranked_chunks() -> None:
    llm = MagicMock()
    rag = MagicMock()
    rag._resolve_query_with_history.return_value = "Ada Lovelace"
    rag._chroma.search.return_value = [{"metadata": {"file_path": "People/Ada.md"}, "score": 0.9}]
    rag._synthesis_patterns.search.return_value = None
    rag._build_context.return_value = "context"
    rag._build_messages.return_value = [{"role": "user", "content": "Ada"}]
    rag._run_chat_attempt.return_value = "Réponse fallback"

    with (
        patch("src.api.chat_fallback_worker.json.load", return_value={"prompt": "Ada", "history": [{"role": "user", "content": "hi"}]}),
        patch("src.api.chat_fallback_worker._iter_note_records", return_value=[]),
        patch("src.api.chat_fallback_worker._build_runtime", return_value=(llm, rag)),
        patch("src.api.chat_fallback_worker.sys.stdout", new=io.StringIO()) as stdout,
    ):
        code = worker.main()

    assert code == 0
    llm.load.assert_called_once_with()
    rag._build_context.assert_called_once_with(rag._chroma.search.return_value, "Ada Lovelace", "general_kw_fallback")
    rag._run_chat_attempt.assert_called_once()
    payload = json.loads(stdout.getvalue())
    assert payload["answer"] == "Réponse fallback"
    assert payload["fallbackMode"] == "filesystem"


def test_main_ignores_unload_errors() -> None:
    llm = MagicMock()
    llm.unload.side_effect = RuntimeError("busy")
    rag = MagicMock()
    rag._resolve_query_with_history.return_value = "Ada Lovelace"
    rag._chroma.search.return_value = []

    with (
        patch("src.api.chat_fallback_worker.json.load", return_value={"prompt": "Ada"}),
        patch("src.api.chat_fallback_worker._iter_note_records", return_value=[]),
        patch("src.api.chat_fallback_worker._build_runtime", return_value=(llm, rag)),
        patch("src.api.chat_fallback_worker.sys.stdout", new=io.StringIO()),
    ):
        assert worker.main() == 0