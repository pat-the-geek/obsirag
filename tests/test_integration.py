"""
Tests d'intégration + benchmarks de bout en bout — ObsiRAG

Ces tests utilisent de vrais fichiers Markdown, ChromaDB en mémoire
et NLP mocké (pas de modèle MLX ni sentence-transformers).
Ils valident que les composants fonctionnent correctement ensemble
et que les seuils de performance clés sont tenus.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.indexer.chunker import TextChunker
from src.indexer.pipeline import IndexingPipeline
from src.vault.parser import NoteParser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_note(vault: Path, name: str, content: str) -> Path:
    p = vault / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_settings(tmp_path: Path) -> MagicMock:
    s = MagicMock()
    vault = tmp_path / "vault"
    vault.mkdir(parents=True)
    s.vault = vault
    s.vault_path = str(vault)
    s.index_state_file = tmp_path / "data" / "index_state.json"
    s.index_state_file.parent.mkdir(parents=True)
    s.chunk_size_words = 50
    s.chunk_overlap_words = 10
    return s


# ---------------------------------------------------------------------------
# Tests d'intégration — Parser + Chunker bout en bout
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestParserChunkerIntegration:
    def test_parse_then_chunk_produces_non_empty_list(self, mock_nlp, tmp_settings, monkeypatch):
        monkeypatch.setattr("src.vault.parser.settings", tmp_settings)
        # Copier une note dans le vault de tmp_settings
        vault_path = Path(tmp_settings.vault_path)
        vault_path.mkdir(parents=True, exist_ok=True)
        note = vault_path / "test.md"
        note.write_text(
            "---\ntitle: Test\ntags: [python]\n---\n\nContenu de test.\n\n"
            "## Section\n\nPlus de contenu ici.\n",
            encoding="utf-8",
        )
        with patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            parser = NoteParser()
            parsed = parser.parse(note)

        assert parsed is not None
        chunker = TextChunker(chunk_size=20, overlap=5)
        chunks = chunker.chunk_note(parsed.metadata, parsed.sections)
        assert len(chunks) > 0
        assert all(c.note_title == "Test" for c in chunks)
        assert all(c.file_path == "test.md" for c in chunks)

    def test_chunk_ids_globally_unique_across_notes(self, tmp_settings, mock_nlp, monkeypatch):
        """Les chunk_id doivent être uniques même pour des notes différentes."""
        monkeypatch.setattr("src.vault.parser.settings", tmp_settings)
        vault = Path(tmp_settings.vault_path)
        vault.mkdir(parents=True, exist_ok=True)

        # Deux notes avec du contenu identique → hash différent (stem différent)
        all_ids: list[str] = []
        for i in range(3):
            note = vault / f"note_{i}.md"
            note.write_text(
                f"---\ntitle: Note {i}\n---\n\nContenu identique pour toutes les notes.\n",
                encoding="utf-8",
            )
            with patch("src.vault.parser.get_nlp", return_value=mock_nlp):
                parser = NoteParser()
                parsed = parser.parse(note)
            if parsed:
                chunker = TextChunker()
                all_ids += [c.chunk_id for c in chunker.chunk_note(parsed.metadata, parsed.sections)]

        assert len(all_ids) == len(set(all_ids)), "Des chunk_id sont dupliqués !"

    def test_metadata_propagated_to_chunks(self, tmp_settings, mock_nlp, monkeypatch):
        monkeypatch.setattr("src.vault.parser.settings", tmp_settings)
        vault = Path(tmp_settings.vault_path)
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "meta_test.md"
        note.write_text(
            "---\ntitle: Titre Spécial\ntags: [tagA, tagB]\n---\n\nContenu.\n",
            encoding="utf-8",
        )
        with patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            parser = NoteParser()
            parsed = parser.parse(note)
        chunker = TextChunker()
        chunks = chunker.chunk_note(parsed.metadata, parsed.sections)
        for chunk in chunks:
            assert "tagA" in chunk.tags
            assert chunk.note_title == "Titre Spécial"
            assert isinstance(chunk.date_modified_ts, float)


# ---------------------------------------------------------------------------
# Tests d'intégration — Indexer + État
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIndexerStateIntegration:
    def test_full_cycle_add_modify_delete(self, tmp_path, mock_nlp):
        """Cycle complet : ajout → vérif état → modification → re-index → suppression."""
        s = _make_settings(tmp_path)
        mock_chroma = MagicMock()
        mock_chroma.count.return_value = 0  # force first run au début

        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline = IndexingPipeline(mock_chroma)

            # 1. Ajout
            note = s.vault / "cycle.md"
            note.write_text("---\ntitle: Cycle\n---\nContenu initial.\n", encoding="utf-8")
            stats = pipeline.index_vault()
            assert stats["added"] == 1
            assert "cycle.md" in pipeline._state

            # 2. Modification
            note.write_text("---\ntitle: Cycle\n---\nContenu modifié!\n", encoding="utf-8")
            mock_chroma.count.return_value = 5  # pas first run
            stats2 = pipeline.index_vault()
            assert stats2["updated"] == 1

            # 3. Suppression physique
            note.unlink()
            stats3 = pipeline.index_vault()
            assert stats3["deleted"] == 1
            assert "cycle.md" not in pipeline._state

    def test_state_persisted_between_instances(self, tmp_path, mock_nlp):
        """L'état d'indexation doit être rechargé correctement après redémarrage."""
        s = _make_settings(tmp_path)
        mock_chroma = MagicMock()

        note = s.vault / "persist.md"
        note.write_text("---\ntitle: Persist\n---\nContenu.\n", encoding="utf-8")

        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            p1 = IndexingPipeline(mock_chroma)
            mock_chroma.count.return_value = 0
            p1.index_vault()
            state_after = dict(p1._state)

        # Recréer le pipeline → doit recharger l'état
        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            p2 = IndexingPipeline(mock_chroma)

        assert p2._state == state_after


# ---------------------------------------------------------------------------
# Benchmarks de bout en bout
# ---------------------------------------------------------------------------

@pytest.mark.perf
class TestEndToEndPerformance:
    def _make_notes(self, vault: Path, n: int, words_per_note: int = 200) -> None:
        vault.mkdir(parents=True, exist_ok=True)
        word = "information"
        for i in range(n):
            body = " ".join([word] * words_per_note)
            (vault / f"note_{i:04d}.md").write_text(
                f"---\ntitle: Note {i}\ntags: [test,perf]\n---\n\n{body}\n\n"
                f"## Section\n\nContenu supplémentaire de la note {i}.\n",
                encoding="utf-8",
            )

    def test_parse_50_notes_under_5s(self, tmp_path, mock_nlp):
        """Parsing de 50 notes (NER mocké) doit prendre moins de 5s."""
        vault = tmp_path / "vault"
        self._make_notes(vault, 50)
        s = MagicMock()
        s.vault = vault

        with (
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            parser = NoteParser()
            t0 = time.perf_counter()
            results = [parser.parse(p) for p in vault.glob("*.md")]
            elapsed = time.perf_counter() - t0

        parsed = [r for r in results if r is not None]
        assert len(parsed) == 50
        assert elapsed < 5.0, f"Parse 50 notes trop lent : {elapsed:.3f}s"

    def test_chunk_50_notes_under_2s(self, tmp_path, mock_nlp):
        """Chunking de 50 notes parsées doit prendre moins de 2s."""
        vault = tmp_path / "vault"
        self._make_notes(vault, 50)
        s = MagicMock()
        s.vault = vault

        with (
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            parser = NoteParser()
            parsed_notes = [parser.parse(p) for p in vault.glob("*.md")]

        chunker = TextChunker(chunk_size=50, overlap=10)
        t0 = time.perf_counter()
        all_chunks = []
        for note in parsed_notes:
            if note:
                all_chunks += chunker.chunk_note(note.metadata, note.sections)
        elapsed = time.perf_counter() - t0

        assert len(all_chunks) > 50
        assert elapsed < 2.0, f"Chunking 50 notes trop lent : {elapsed:.3f}s"

    def test_reindex_detects_unchanged_notes_fast(self, tmp_path, mock_nlp):
        """Re-indexation sans changement : 50 notes skippées en < 2s."""
        import hashlib

        s = _make_settings(tmp_path)
        vault = s.vault
        self._make_notes(vault, 50)

        mock_chroma = MagicMock()
        mock_chroma.count.return_value = 50  # pas first run

        # Pré-remplir l'état
        state = {}
        for p in vault.glob("*.md"):
            state[str(p.relative_to(vault))] = hashlib.md5(p.read_bytes()).hexdigest()

        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline = IndexingPipeline(mock_chroma)
            pipeline._state = state

            t0 = time.perf_counter()
            stats = pipeline.index_vault()
            elapsed = time.perf_counter() - t0

        assert stats["skipped"] == 50
        assert elapsed < 2.0, f"Re-indexation skip 50 notes trop lente : {elapsed:.3f}s"
        # Aucun appel LLM/chroma
        mock_chroma.add_chunks.assert_not_called()

    def test_hash_throughput(self, tmp_path):
        """Throughput hachage MD5 : au moins 500 fichiers/seconde."""
        vault = tmp_path / "vault"
        vault.mkdir()
        for i in range(100):
            (vault / f"note_{i}.md").write_text("a" * 2000, encoding="utf-8")

        t0 = time.perf_counter()
        for p in vault.glob("*.md"):
            IndexingPipeline._file_hash(p)
        elapsed = time.perf_counter() - t0

        throughput = 100 / elapsed
        assert throughput >= 500, f"Hachage trop lent : {throughput:.0f} fichiers/s (min 500)"

    def test_chunker_throughput_words_per_second(self):
        """TextChunker doit traiter au moins 50 000 mots/seconde."""
        from src.vault.parser import NoteEntities, NoteMetadata, NoteSection
        from datetime import datetime

        meta = NoteMetadata(
            file_path="bench.md", title="Bench",
            date_modified=datetime(2026, 1, 1), date_created=datetime(2026, 1, 1),
            tags=[], wikilinks=[], entities=NoteEntities(),
            frontmatter={}, file_hash="bench",
        )
        # 5000 mots
        content = " ".join([f"mot{i}" for i in range(5000)])
        sections = [NoteSection(title="", level=0, content=content)]
        chunker = TextChunker(chunk_size=100, overlap=20)

        t0 = time.perf_counter()
        chunks = chunker.chunk_note(meta, sections)
        elapsed = time.perf_counter() - t0

        wps = 5000 / elapsed
        assert wps >= 50_000, f"Chunker trop lent : {wps:.0f} mots/s (min 50 000)"
        assert len(chunks) > 0
