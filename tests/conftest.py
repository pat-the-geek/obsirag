"""
Configuration partagée des tests ObsiRAG.
Fournit des fixtures réutilisables sans dépendances externes
(pas de modèle MLX, pas de store vecteurs réel, pas de spaCy).
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import time
from contextlib import contextmanager

from src.config import Settings


# ---------------------------------------------------------------------------
# Helpers de performance
# ---------------------------------------------------------------------------

@contextmanager
def assert_duration(max_seconds: float, label: str = ""):
    """Context manager : lève AssertionError si le bloc dépasse max_seconds."""
    t0 = time.perf_counter()
    yield
    elapsed = time.perf_counter() - t0
    assert elapsed <= max_seconds, (
        f"Performance {label!r} : {elapsed:.3f}s > seuil {max_seconds}s"
    )


@pytest.fixture
def perf_timer():
    """Fixture renvoyant un callable timer(label, max_s) utilisable dans les tests."""
    results: list[dict] = []

    class Timer:
        def measure(self, label: str, max_seconds: float):
            return assert_duration(max_seconds, label)

        def record(self, label: str, elapsed: float) -> None:
            results.append({"label": label, "elapsed": elapsed})

        def summary(self) -> str:
            return "  ".join(f"{r['label']}: {r['elapsed']:.3f}s" for r in results)

    return Timer()


# ---------------------------------------------------------------------------
# Settings en mémoire (override les chemins vers /tmp)
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_settings(tmp_path):
    """Settings with all paths redirected to a temp directory."""
    s = Settings(
        vault_path=str(tmp_path / "vault"),
        app_data_dir=str(tmp_path / "data"),
        obsidian_vault_name="",
        embedding_model="paraphrase-multilingual-MiniLM-L12-v2",
        chroma_collection="test_collection",
        log_level="WARNING",
        log_dir=str(tmp_path / "logs"),
    )
    (tmp_path / "vault").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True)
    return s


# ---------------------------------------------------------------------------
# Vault avec notes de test
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_vault(tmp_path):
    """Coffre minimal avec quelques notes Markdown."""
    vault = tmp_path / "vault"
    vault.mkdir()

    (vault / "Note Python.md").write_text(
        "---\ntitle: Python pour data science\ntags: [python, data]\n---\n\n"
        "Python est un langage de programmation polyvalent.\n\n"
        "## Machine Learning\n\nScikit-learn est une bibliothèque de ML.\n\n"
        "## Pandas\n\nPandas permet de manipuler des données tabulaires.\n",
        encoding="utf-8",
    )

    (vault / "Note IA.md").write_text(
        "---\ntitle: Intelligence Artificielle\ntags: [ia, ml]\n---\n\n"
        "L'IA transforme de nombreux secteurs.\n\n"
        "## LLM\n\nLes grands modèles de langage sont entraînés sur des milliards de tokens.\n"
        "Voir aussi [[Note Python]] pour les outils.\n",
        encoding="utf-8",
    )

    (vault / "Note vide.md").write_text(
        "---\ntitle: Note vide\n---\n\n",
        encoding="utf-8",
    )

    # Note dans un sous-dossier
    sub = vault / "projets"
    sub.mkdir()
    (sub / "Projet Alpha.md").write_text(
        "---\ntitle: Projet Alpha\ntags: [projet]\n---\n\n"
        "Description du projet Alpha.\n\n"
        "## Objectifs\n\nAtteindre 100 utilisateurs.\n",
        encoding="utf-8",
    )

    return vault


@pytest.fixture
def note_path(sample_vault):
    """Chemin de la note Python."""
    return sample_vault / "Note Python.md"


# ---------------------------------------------------------------------------
# Mocks des dépendances lourdes
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_nlp():
    """Mock spaCy NLP — retourne une liste d'entités vide par défaut."""
    nlp = MagicMock()
    doc = MagicMock()
    doc.ents = []
    nlp.return_value = doc
    nlp.pipe_names = ["ner"]
    return nlp


@pytest.fixture
def mock_embedding_fn():
    """Mock de la fonction d'embedding vectoriel."""
    fn = MagicMock()
    fn.return_value = [[0.1] * 384]
    return fn


@pytest.fixture
def mock_llm():
    """Mock du client MLX."""
    llm = MagicMock()
    llm.is_available.return_value = True
    llm.is_loaded.return_value = True
    llm.chat.return_value = "Réponse de test du LLM."
    llm.stream.return_value = iter(["Réponse ", "de ", "test."])
    return llm


@pytest.fixture
def mock_chroma(mock_embedding_fn):
    """Mock ChromaStore minimal."""
    chroma = MagicMock()
    chroma.count.return_value = 10
    chroma.list_notes.return_value = [
        {
            "file_path": "Note Python.md",
            "title": "Python pour data science",
            "date_modified": "2026-04-01T10:00:00",
            "date_created": "2026-01-01T10:00:00",
            "tags": ["python", "data"],
            "wikilinks": [],
        }
    ]
    chroma.search.return_value = [
        {
            "chunk_id": "abc123_0",
            "text": "Python est un langage polyvalent.",
            "metadata": {
                "note_title": "Python pour data science",
                "file_path": "Note Python.md",
                "date_modified": "2026-04-01T10:00:00",
                "tags": "python,data",
                "wikilinks": "",
            },
            "score": 0.95,
        }
    ]
    chroma.search_by_tags.return_value = chroma.search.return_value
    chroma.search_by_date_range.return_value = chroma.search.return_value
    chroma.search_by_entity.return_value = chroma.search.return_value
    chroma.search_by_keyword.return_value = chroma.search.return_value
    # API publique complète de ChromaStore
    chroma.count_notes.return_value = 1
    chroma.list_user_notes.return_value = chroma.list_notes.return_value
    chroma.list_generated_notes.return_value = []
    chroma.list_recent_notes.return_value = chroma.list_notes.return_value
    chroma.get_chunks_by_note_title.return_value = []
    chroma.get_chunks_by_file_path.return_value = []
    return chroma


# ---------------------------------------------------------------------------
# NoteMetadata / ParsedNote de test
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_metadata():
    from src.vault.parser import NoteEntities, NoteMetadata
    return NoteMetadata(
        file_path="Note Python.md",
        title="Python pour data science",
        date_modified=datetime(2026, 4, 1, 10, 0),
        date_created=datetime(2026, 1, 1, 10, 0),
        tags=["python", "data"],
        wikilinks=[],
        entities=NoteEntities(persons=[], orgs=["Scikit-learn"], locations=[], misc=[]),
        frontmatter={},
        file_hash="deadbeef",
    )


@pytest.fixture
def sample_sections():
    from src.vault.parser import NoteSection
    return [
        NoteSection(title="", level=0, content="Python est un langage polyvalent."),
        NoteSection(title="Machine Learning", level=2, content="Scikit-learn est une bibliothèque."),
    ]
