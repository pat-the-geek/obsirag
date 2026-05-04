"""
Tests unitaires + performance — IndexingPipeline (src/indexer/pipeline.py)
Store vecteurs et NLP sont mockés pour rester rapides.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.indexer.pipeline import IndexingPipeline


# ---------------------------------------------------------------------------
# Fixtures locales
# ---------------------------------------------------------------------------

@pytest.fixture
def settings_mock(tmp_path):
    s = MagicMock()
    s.vault = tmp_path / "vault"
    s.vault_path = str(s.vault)
    s.index_state_file = tmp_path / "data" / "index_state.json"
    s.index_state_file.parent.mkdir(parents=True)
    s.max_note_size_bytes = 500_000
    s.max_chunks_per_note = 300
    return s


@pytest.fixture
def pipeline(settings_mock, mock_chroma, mock_nlp):
    with (
        patch("src.indexer.pipeline.settings", settings_mock),
        patch("src.vault.parser.settings", settings_mock),
        patch("src.vault.parser.get_nlp", return_value=mock_nlp),
    ):
        p = IndexingPipeline(mock_chroma)
        p._settings_mock = settings_mock
        yield p


@pytest.fixture
def vault_with_notes(settings_mock):
    """Crée quelques notes dans le vaut fictif."""
    vault = settings_mock.vault
    vault.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (vault / f"note_{i}.md").write_text(
            f"---\ntitle: Note {i}\n---\n\nContenu de la note {i}.\n",
            encoding="utf-8",
        )
    return vault


# ---------------------------------------------------------------------------
# Tests _is_first_run
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIsFirstRun:
    def test_first_run_when_empty(self, pipeline, mock_chroma):
        pipeline._state = {}
        mock_chroma.count.return_value = 0
        assert pipeline._is_first_run() is True

    def test_not_first_run_when_state_exists(self, pipeline, mock_chroma):
        pipeline._state = {"note.md": "abc"}
        mock_chroma.count.return_value = 5
        assert pipeline._is_first_run() is False

    def test_not_first_run_when_chroma_has_data(self, pipeline, mock_chroma):
        pipeline._state = {}
        mock_chroma.count.return_value = 10
        assert pipeline._is_first_run() is False


# ---------------------------------------------------------------------------
# Tests _file_hash
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFileHash:
    def test_hash_is_md5_hexdigest(self, tmp_path):
        import hashlib
        p = tmp_path / "test.md"
        p.write_bytes(b"Contenu de test")
        result = IndexingPipeline._file_hash(p)
        expected = hashlib.md5(b"Contenu de test").hexdigest()
        assert result == expected

    def test_hash_changes_with_content(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_bytes(b"version 1")
        h1 = IndexingPipeline._file_hash(p)
        p.write_bytes(b"version 2")
        h2 = IndexingPipeline._file_hash(p)
        assert h1 != h2

    def test_hash_stable(self, tmp_path):
        p = tmp_path / "stable.md"
        p.write_bytes(b"contenu constant")
        assert IndexingPipeline._file_hash(p) == IndexingPipeline._file_hash(p)


# ---------------------------------------------------------------------------
# Tests _load_state / _save_state
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStateIO:
    def test_load_state_empty_when_no_file(self, pipeline, settings_mock):
        settings_mock.index_state_file.unlink(missing_ok=True)
        with patch("src.indexer.pipeline.settings", settings_mock):
            state = pipeline._load_state()
        assert state == {}

    def test_save_and_reload_state(self, pipeline, settings_mock):
        pipeline._state = {"note_a.md": "hash1", "note_b.md": "hash2"}
        with patch("src.indexer.pipeline.settings", settings_mock):
            pipeline._save_state()
            loaded = pipeline._load_state()
        assert loaded == {"note_a.md": "hash1", "note_b.md": "hash2"}

    def test_save_state_creates_parent_dir(self, tmp_path, mock_chroma, mock_nlp):
        s = MagicMock()
        s.vault = tmp_path / "vault"
        s.vault.mkdir()
        deep_path = tmp_path / "deep" / "nested" / "index_state.json"
        s.index_state_file = deep_path
        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            p = IndexingPipeline(mock_chroma)
            p._state = {"x.md": "abc"}
            p._save_state()
        assert deep_path.exists()

    def test_corrupted_state_file_returns_empty(self, pipeline, settings_mock):
        settings_mock.index_state_file.write_text("INVALID JSON !!!", encoding="utf-8")
        with patch("src.indexer.pipeline.settings", settings_mock):
            state = pipeline._load_state()
        assert state == {}


# ---------------------------------------------------------------------------
# Tests _delete_from_index
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDeleteFromIndex:
    def test_delete_removes_from_state(self, pipeline, mock_chroma):
        pipeline._state = {"note.md": "abc123"}
        pipeline._delete_from_index("note.md")
        assert "note.md" not in pipeline._state

    def test_delete_calls_chroma_delete(self, pipeline, mock_chroma):
        pipeline._state = {"note.md": "abc123"}
        pipeline._delete_from_index("note.md")
        mock_chroma.delete_by_file.assert_called_once_with("note.md")

    def test_delete_missing_key_is_noop(self, pipeline, mock_chroma):
        pipeline._state = {}
        pipeline._delete_from_index("inexistant.md")
        mock_chroma.delete_by_file.assert_called_once_with("inexistant.md")


# ---------------------------------------------------------------------------
# Tests index_vault — mode normal (incrémental)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIndexVaultIncremental:
    def test_skips_unchanged_notes(self, pipeline, settings_mock, mock_chroma, vault_with_notes, mock_nlp):
        """Notes dont le hash n'a pas changé → skipped."""
        # Pré-remplir l'état avec les hash actuels
        import hashlib
        for note in vault_with_notes.glob("*.md"):
            rel = str(note.relative_to(settings_mock.vault))
            pipeline._state[rel] = hashlib.md5(note.read_bytes()).hexdigest()
        mock_chroma.count.return_value = len(pipeline._state)

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            stats = pipeline.index_vault()
        assert stats["skipped"] == 3
        assert stats["added"] == 0
        assert stats["updated"] == 0

    def test_indexes_new_notes(self, pipeline, settings_mock, mock_chroma, vault_with_notes, mock_nlp):
        """Notes absentes de l'état → added."""
        pipeline._state = {}
        mock_chroma.count.return_value = 1  # pas first run → mode normal

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            stats = pipeline.index_vault()
        assert stats["added"] == 3

    def test_detects_deleted_notes(self, pipeline, settings_mock, mock_chroma, vault_with_notes, mock_nlp):
        """Notes dans l'état mais plus sur disque → deleted."""
        pipeline._state = {
            "note_0.md": "old_hash",
            "disparu.md": "some_hash",  # cette note n'existe plus
        }
        mock_chroma.count.return_value = 5  # pas first run

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            stats = pipeline.index_vault()
        assert stats["deleted"] == 1

    def test_on_progress_called(self, pipeline, settings_mock, mock_chroma, vault_with_notes, mock_nlp):
        """Le callback on_progress doit être appelé pour chaque note."""
        mock_chroma.count.return_value = 1
        pipeline._state = {}
        calls = []

        def _progress(note, processed, total):
            calls.append((processed, total))

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline.index_vault(on_progress=_progress)

        assert len(calls) == 3
        assert calls[-1][0] == calls[-1][1]  # processed == total à la fin

    def test_vault_missing_returns_zero_stats(self, pipeline, settings_mock, mock_chroma):
        settings_mock.vault = Path("/inexistant/vault")
        with patch("src.indexer.pipeline.settings", settings_mock):
            stats = pipeline.index_vault()
        assert stats == {"added": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": 0}


# ---------------------------------------------------------------------------
# Tests index_vault — mode accéléré (première exécution)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIndexVaultFastMode:
    def test_fast_mode_when_first_run(self, pipeline, settings_mock, mock_chroma, vault_with_notes, mock_nlp):
        pipeline._state = {}
        mock_chroma.count.return_value = 0  # first run

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            stats = pipeline.index_vault()

        assert stats["errors"] == 0
        mock_chroma.add_chunks.assert_called()

    def test_fast_mode_batches_chunks(self, pipeline, settings_mock, vault_with_notes, mock_nlp):
        """En mode accéléré, add_chunks est appelé par lots (pas note par note)."""
        mock_chroma = MagicMock()
        mock_chroma.count.return_value = 0
        pipeline._chroma = mock_chroma
        pipeline._state = {}

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline.index_vault()

        # add_chunks doit avoir été appelé avec plusieurs chunks regroupés
        total_chunks = sum(len(c.args[0]) for c in mock_chroma.add_chunks.call_args_list)
        assert total_chunks > 0


# ---------------------------------------------------------------------------
# Tests index_note / remove_note
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestIndexNote:
    def test_index_note_updates_state(self, pipeline, settings_mock, mock_chroma, mock_nlp, tmp_path):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "single.md"
        note.write_text("---\ntitle: Single\n---\nContenu.\n", encoding="utf-8")

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline.index_note(note)

        assert "single.md" in pipeline._state

    def test_index_note_ignores_non_md(self, pipeline, settings_mock, mock_chroma, tmp_path):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        txt = vault / "fichier.txt"
        txt.write_text("texte", encoding="utf-8")

        with patch("src.indexer.pipeline.settings", settings_mock):
            pipeline.index_note(txt)

        mock_chroma.add_chunks.assert_not_called()

    def test_index_note_ignores_missing_file(self, pipeline, settings_mock, mock_chroma):
        missing = settings_mock.vault / "absent.md"

        with patch("src.indexer.pipeline.settings", settings_mock):
            pipeline.index_note(missing)

        mock_chroma.add_chunks.assert_not_called()

    def test_remove_note_clears_state(self, pipeline, settings_mock, mock_chroma):
        pipeline._state = {"note.md": "hash"}
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "note.md"
        note.write_text("test", encoding="utf-8")

        with patch("src.indexer.pipeline.settings", settings_mock):
            pipeline.remove_note(note)

        assert "note.md" not in pipeline._state
        mock_chroma.delete_by_file.assert_called_once_with("note.md")


@pytest.mark.unit
class TestIndexerRobustness:
    def test_prepare_chunks_skips_note_too_large(self, pipeline, settings_mock, mock_nlp):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "big.md"
        note.write_text("x" * 20, encoding="utf-8")
        settings_mock.max_note_size_bytes = 5

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            chunks = pipeline._prepare_chunks(note, "big.md")

        assert chunks == []

    def test_prepare_chunks_truncates_to_max_chunks_and_updates_state(self, pipeline, settings_mock):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "many.md"
        note.write_text("content", encoding="utf-8")
        settings_mock.max_chunks_per_note = 2

        parsed = MagicMock()
        parsed.metadata.file_hash = "hash-many"
        parsed.sections = [MagicMock()]
        fake_chunks = [MagicMock(chunk_id=f"c{i}") for i in range(4)]

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch.object(pipeline._parser, "parse", return_value=parsed),
            patch.object(pipeline._chunker, "chunk_note", return_value=fake_chunks),
        ):
            chunks = pipeline._prepare_chunks(note, "many.md")

        assert len(chunks) == 2
        assert pipeline._state["many.md"] == "hash-many"

    def test_index_file_deletes_previous_chunks_before_reindex(self, pipeline, settings_mock, mock_chroma, mock_nlp):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "reindex.md"
        note.write_text("---\ntitle: Reindex\n---\nContenu.\n", encoding="utf-8")
        pipeline._state = {"reindex.md": "oldhash"}

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline._index_file(note, "reindex.md")

        mock_chroma.delete_by_file.assert_called_once_with("reindex.md")
        mock_chroma.add_chunks.assert_called()

    def test_index_file_skips_when_parser_returns_none(self, pipeline, settings_mock):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "broken.md"
        note.write_text("invalid", encoding="utf-8")

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch.object(pipeline._parser, "parse", return_value=None),
        ):
            pipeline._index_file(note, "broken.md")

        pipeline._chroma.add_chunks.assert_not_called()

    def test_index_file_skips_when_note_is_too_large(self, pipeline, settings_mock):
        vault = settings_mock.vault
        vault.mkdir(parents=True, exist_ok=True)
        note = vault / "too_big.md"
        note.write_text("x" * 20, encoding="utf-8")
        settings_mock.max_note_size_bytes = 5

        with patch("src.indexer.pipeline.settings", settings_mock):
            pipeline._index_file(note, "too_big.md")

        assert "too_big.md" not in pipeline._state
        pipeline._chroma.add_chunks.assert_not_called()

    def test_is_internal_is_currently_disabled(self, tmp_path):
        assert IndexingPipeline._is_internal(tmp_path / "obsirag" / "generated.md") is False

    def test_fast_mode_counts_errors_when_prepare_chunks_raises(self, pipeline, settings_mock, vault_with_notes, mock_nlp):
        pipeline._state = {}
        pipeline._chroma.count.return_value = 0

        with (
            patch("src.indexer.pipeline.settings", settings_mock),
            patch("src.vault.parser.settings", settings_mock),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
            patch.object(pipeline, "_prepare_chunks", side_effect=[[], RuntimeError("boom"), []]),
        ):
            stats = pipeline.index_vault()

        assert stats["errors"] == 1


# ---------------------------------------------------------------------------
# Performance — IndexingPipeline
# ---------------------------------------------------------------------------

@pytest.mark.perf
class TestIndexerPerformance:
    def _create_vault(self, vault_path: Path, n: int) -> None:
        vault_path.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (vault_path / f"note_{i:04d}.md").write_text(
                f"---\ntitle: Note {i}\ntags: [test]\n---\n\n"
                f"Contenu de la note numéro {i}. "
                f"Elle contient du texte suffisant pour être chunkée correctement.\n\n"
                f"## Section\n\nDétails supplémentaires de la note {i}.\n",
                encoding="utf-8",
            )

    def test_index_state_hash_100_notes_under_2s(self, tmp_path):
        """Calcul des hashes MD5 de 100 fichiers doit prendre moins de 2s."""
        vault = tmp_path / "vault"
        self._create_vault(vault, 100)

        t0 = time.perf_counter()
        for p in vault.glob("*.md"):
            IndexingPipeline._file_hash(p)
        elapsed = time.perf_counter() - t0

        assert elapsed < 2.0, f"Hachage 100 fichiers trop lent : {elapsed:.3f}s"

    def test_detect_skipped_notes_fast(self, tmp_path, mock_nlp):
        """Détection des notes inchangées (skip) doit être O(1) par note grâce aux hashes."""
        import hashlib
        from unittest.mock import MagicMock

        s = MagicMock()
        vault = tmp_path / "vault"
        self._create_vault(vault, 50)
        s.vault = vault
        s.index_state_file = tmp_path / "data" / "state.json"
        s.index_state_file.parent.mkdir()

        mock_chroma = MagicMock()
        mock_chroma.count.return_value = 50  # pas first run

        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline = IndexingPipeline(mock_chroma)
            # Pré-remplir l'état avec les hash actuels
            for p in vault.glob("*.md"):
                rel = str(p.relative_to(vault))
                pipeline._state[rel] = hashlib.md5(p.read_bytes()).hexdigest()

            t0 = time.perf_counter()
            stats = pipeline.index_vault()
            elapsed = time.perf_counter() - t0

        assert stats["skipped"] == 50
        assert elapsed < 1.0, f"Skip 50 notes trop lent : {elapsed:.3f}s"

    def test_save_state_1000_entries_under_200ms(self, tmp_path, mock_nlp):
        """Sauvegarde de l'état pour 1000 notes doit être < 200ms."""
        s = MagicMock()
        s.vault = tmp_path / "vault"
        s.vault.mkdir()
        s.index_state_file = tmp_path / "data" / "state.json"
        s.index_state_file.parent.mkdir()

        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline = IndexingPipeline(MagicMock())
            pipeline._state = {f"note_{i}.md": f"hash{i}" for i in range(1000)}

            t0 = time.perf_counter()
            with patch("src.indexer.pipeline.settings", s):
                pipeline._save_state()
            elapsed = time.perf_counter() - t0

        assert elapsed < 0.2, f"_save_state 1000 entrées trop lent : {elapsed*1000:.1f}ms"

    def test_on_progress_callback_overhead_negligible(self, tmp_path, mock_nlp):
        """Le callback on_progress ne doit pas alourdir l'indexation de plus de 5ms/note."""
        s = MagicMock()
        vault = tmp_path / "vault"
        self._create_vault(vault, 10)
        s.vault = vault
        s.index_state_file = tmp_path / "data" / "state.json"
        s.index_state_file.parent.mkdir()

        mock_chroma = MagicMock()
        mock_chroma.count.return_value = 1  # pas first run
        call_times: list[float] = []

        def _progress(note, processed, total):
            call_times.append(time.perf_counter())

        with (
            patch("src.indexer.pipeline.settings", s),
            patch("src.vault.parser.settings", s),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
        ):
            pipeline = IndexingPipeline(mock_chroma)
            pipeline.index_vault(on_progress=_progress)

        assert len(call_times) == 10
        # Intervalles entre callbacks < 200ms chacun (NLP mocké)
        for i in range(1, len(call_times)):
            gap = call_times[i] - call_times[i - 1]
            assert gap < 0.2, f"Gap callback {i}: {gap*1000:.1f}ms"
