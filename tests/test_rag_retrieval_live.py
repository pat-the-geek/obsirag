"""
Tests end-to-end RAG sur coffre réel (live).

Ces tests écrivent 3 notes fictives avec des noms totalement uniques dans le
coffre réel, les indexent via IndexingPipeline, lancent des requêtes RAG et
vérifient les réponses — puis suppriment les notes et nettoient l'index.

Chaque note contient un mot-clé inventé introuvable ailleurs dans le coffre :
  - ZEPHYRIUM   → minéral fictif, note sur ses propriétés thermiques
  - VALTOREX    → ville fictive, note sur son architecture brutaliste
  - PLUMBIFEX   → organisme fictif, note sur sa biologie aquatique

Exécuter uniquement ces tests :
    pytest -m live tests/test_rag_retrieval_live.py -v

Pré-requis :
  • Ollama accessible (OLLAMA_BASE_URL / ollama_base_url dans .env)
  • Euria configurée (EURIA_URL + EURIA_BEARER) — sinon les tests Euria sont skippés
"""
from __future__ import annotations

import pytest

from pathlib import Path
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.indexer.pipeline import IndexingPipeline
from src.ai.rag import RAGPipeline
from src.ai.ollama_client import OllamaClient
from src.ai.euria_client import EuriaClient

# ---------------------------------------------------------------------------
# Définition des 3 notes de test
# ---------------------------------------------------------------------------

_TEST_NOTES: list[dict] = [
    {
        "filename": "__obsirag_test_zephyrium.md",
        "content": (
            "---\ntitle: Zephyrium\ntags: [test-live, mineraux]\n---\n\n"
            "# Zephyrium\n\n"
            "Le **Zephyrium** est un minéral fictif à très haute conductivité thermique,\n"
            "découvert dans les montagnes du Nordavar en 2042.\n"
            "Sa couleur est bleu-violet irisé et sa dureté est de 9,4 sur l'échelle de Mohs.\n"
            "Le Zephyrium fond à 3 847 °C et est utilisé dans la fabrication de réacteurs à\n"
            "fusion froide de quatrième génération.\n"
            "Sa formule chimique est Zp₃(SiO₄)₂·H₂O et il cristallise dans le système hexagonal.\n"
        ),
        "query": "Quelles sont les propriétés du Zephyrium ?",
        "expected_keywords": ["zephyrium", "thermique", "mohs"],
    },
    {
        "filename": "__obsirag_test_valtorex.md",
        "content": (
            "---\ntitle: Valtorex\ntags: [test-live, villes]\n---\n\n"
            "# Valtorex\n\n"
            "**Valtorex** est une ville fictive de 840 000 habitants située sur l'archipel de Threnoria.\n"
            "Elle est réputée pour son architecture brutaliste du XXIIe siècle et ses 47 tours\n"
            "en béton apparent construites entre 2078 et 2091.\n"
            "Le maire actuel est Elsira Vondrak, élue en 2099.\n"
            "Valtorex accueille chaque année le festival international du Béton Vivant\n"
            "qui attire plus de 200 000 visiteurs.\n"
        ),
        "query": "Parle-moi de la ville de Valtorex.",
        "expected_keywords": ["valtorex", "brutaliste", "habitants"],
    },
    {
        "filename": "__obsirag_test_plumbifex.md",
        "content": (
            "---\ntitle: Plumbifex\ntags: [test-live, biologie]\n---\n\n"
            "# Plumbifex\n\n"
            "Le **Plumbifex** est un organisme aquatique fictif de la famille des Hexopodidae.\n"
            "Il vit à des profondeurs de 400 à 1 200 mètres dans l'océan de Solmarine.\n"
            "Sa particularité est de produire une bioluminescence pulsée à 3 Hz\n"
            "grâce à des organes spécialisés appelés lumicules.\n"
            "Le Plumbifex se nourrit exclusivement de microalgues abyssales\n"
            "et peut vivre jusqu'à 120 ans.\n"
        ),
        "query": "Qu'est-ce que le Plumbifex ?",
        "expected_keywords": ["plumbifex", "bioluminescence", "aquatique"],
    },
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def vault_path() -> Path:
    return Path(settings.vault_path)


@pytest.fixture(scope="module")
def chroma() -> ChromaStore:
    return ChromaStore()


@pytest.fixture(scope="module")
def indexer(chroma: ChromaStore) -> IndexingPipeline:
    return IndexingPipeline(chroma)


@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown(vault_path: Path, indexer: IndexingPipeline):
    """Écrit les 3 notes, les indexe, yield, puis les supprime et nettoie l'index."""
    created: list[Path] = []
    for note_def in _TEST_NOTES:
        note_path = vault_path / note_def["filename"]
        note_path.write_text(note_def["content"], encoding="utf-8")
        created.append(note_path)
        indexer.index_note(note_path)

    yield

    for note_path in created:
        if note_path.exists():
            indexer.remove_note(note_path)
            note_path.unlink(missing_ok=True)


@pytest.fixture(scope="module")
def rag_ollama(chroma: ChromaStore) -> RAGPipeline:
    llm = OllamaClient()
    return RAGPipeline(chroma, llm)


@pytest.fixture(scope="module")
def rag_euria(chroma: ChromaStore) -> RAGPipeline | None:
    try:
        llm = EuriaClient()
        return RAGPipeline(chroma, llm)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_answer(answer: str, expected_keywords: list[str], provider: str, query: str) -> None:
    """Vérifie qu'au moins un mot-clé attendu apparaît dans la réponse (insensible à la casse)."""
    answer_lower = answer.lower()
    matched = [kw for kw in expected_keywords if kw.lower() in answer_lower]
    assert matched, (
        f"[{provider}] Réponse à '{query}' ne contient aucun mot-clé attendu "
        f"({expected_keywords}).\nRéponse reçue:\n{answer[:600]}"
    )
    # La réponse ne doit pas être le sentinel d'absence d'info
    assert "pas dans ton coffre" not in answer_lower, (
        f"[{provider}] Réponse sentinel reçue pour '{query}'"
    )


# ---------------------------------------------------------------------------
# Tests Ollama
# ---------------------------------------------------------------------------

class TestRagRetrievalOllama:
    """Requêtes RAG sur les 3 notes de test via Ollama (inférence locale)."""

    def test_zephyrium_ollama(self, rag_ollama: RAGPipeline) -> None:
        note = _TEST_NOTES[0]
        answer, sources = rag_ollama.query(note["query"])
        _check_answer(answer, note["expected_keywords"], "Ollama", note["query"])
        assert sources, "Aucune source retournée pour Zephyrium (Ollama)"

    def test_valtorex_ollama(self, rag_ollama: RAGPipeline) -> None:
        note = _TEST_NOTES[1]
        answer, sources = rag_ollama.query(note["query"])
        _check_answer(answer, note["expected_keywords"], "Ollama", note["query"])
        assert sources, "Aucune source retournée pour Valtorex (Ollama)"

    def test_plumbifex_ollama(self, rag_ollama: RAGPipeline) -> None:
        note = _TEST_NOTES[2]
        answer, sources = rag_ollama.query(note["query"])
        _check_answer(answer, note["expected_keywords"], "Ollama", note["query"])
        assert sources, "Aucune source retournée pour Plumbifex (Ollama)"


# ---------------------------------------------------------------------------
# Tests Euria (skippés si credentials absents)
# ---------------------------------------------------------------------------

class TestRagRetrievalEuria:
    """Requêtes RAG sur les 3 notes de test via Euria (sans recherche web)."""

    def test_zephyrium_euria(self, rag_euria: RAGPipeline | None) -> None:
        if rag_euria is None:
            pytest.skip("Euria non configurée (EURIA_URL / EURIA_BEARER manquants)")
        note = _TEST_NOTES[0]
        answer, sources = rag_euria.query(note["query"])
        _check_answer(answer, note["expected_keywords"], "Euria", note["query"])
        assert sources, "Aucune source retournée pour Zephyrium (Euria)"

    def test_valtorex_euria(self, rag_euria: RAGPipeline | None) -> None:
        if rag_euria is None:
            pytest.skip("Euria non configurée (EURIA_URL / EURIA_BEARER manquants)")
        note = _TEST_NOTES[1]
        answer, sources = rag_euria.query(note["query"])
        _check_answer(answer, note["expected_keywords"], "Euria", note["query"])
        assert sources, "Aucune source retournée pour Valtorex (Euria)"

    def test_plumbifex_euria(self, rag_euria: RAGPipeline | None) -> None:
        if rag_euria is None:
            pytest.skip("Euria non configurée (EURIA_URL / EURIA_BEARER manquants)")
        note = _TEST_NOTES[2]
        answer, sources = rag_euria.query(note["query"])
        _check_answer(answer, note["expected_keywords"], "Euria", note["query"])
        assert sources, "Aucune source retournée pour Plumbifex (Euria)"
