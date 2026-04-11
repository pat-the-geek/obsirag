from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ai.rag import RAGPipeline
from src.indexer.pipeline import IndexingPipeline
from src.learning.autolearn import AutoLearner


class RecordingChroma:
    def __init__(self) -> None:
        self.chunks = []

    def add_chunks(self, chunks):
        ids = {c.chunk_id for c in chunks}
        self.chunks = [c for c in self.chunks if c.chunk_id not in ids]
        self.chunks.extend(chunks)

    def delete_by_file(self, rel_path: str):
        self.chunks = [c for c in self.chunks if c.file_path != rel_path]

    def count(self):
        return len(self.chunks)

    def list_notes(self):
        by_file = {}
        for chunk in self.chunks:
            by_file.setdefault(chunk.file_path, {
                "file_path": chunk.file_path,
                "title": chunk.note_title,
                "date_modified": chunk.date_modified,
                "date_created": chunk.date_created,
                "tags": [t for t in chunk.tags.split(",") if t],
                "wikilinks": [w for w in chunk.wikilinks.split(",") if w],
            })
        return sorted(by_file.values(), key=lambda n: n["date_modified"], reverse=True)

    def get_recently_modified(self, since):
        since_iso = since.isoformat()
        return [n for n in self.list_notes() if n["date_modified"] >= since_iso]

    def _to_result(self, chunk, score: float = 0.96):
        return {
            "chunk_id": chunk.chunk_id,
            "text": chunk.text,
            "metadata": chunk.as_metadata(),
            "score": score,
        }

    def search(self, query: str, top_k: int = 8, where: dict | None = None):
        query_low = query.lower()
        results = []
        for chunk in self.chunks:
            meta = chunk.as_metadata()
            if where:
                and_filters = where.get("$and", [])
                ok = True
                for condition in and_filters:
                    for key, bounds in condition.items():
                        value = meta.get(key)
                        if value is None:
                            ok = False
                            break
                        if "$gte" in bounds and value < bounds["$gte"]:
                            ok = False
                        if "$lte" in bounds and value > bounds["$lte"]:
                            ok = False
                    if not ok:
                        break
                if not ok:
                    continue
            haystack = f"{chunk.note_title} {chunk.text} {chunk.tags}".lower()
            if query_low in haystack or any(word in haystack for word in query_low.split() if len(word) >= 3):
                results.append(self._to_result(chunk))
        return results[:top_k]

    def search_by_keyword(self, keyword: str, top_k: int = 10):
        return self.search(keyword, top_k=top_k)

    def search_by_note_title(self, title: str, top_k: int = 10):
        title_low = title.lower()
        results = [self._to_result(c, score=0.98) for c in self.chunks if title_low in c.note_title.lower()]
        return results[:top_k]

    def search_by_tags(self, tags: list[str], top_k: int = 8):
        wanted = {t.lower() for t in tags}
        results = []
        for chunk in self.chunks:
            tag_set = {t.lower() for t in chunk.tags.split(",") if t}
            if wanted & tag_set:
                results.append(self._to_result(chunk))
        return results[:top_k]

    def search_by_date_range(self, query: str, since: datetime, until=None, top_k: int = 8):
        return [r for r in self.search(query, top_k=top_k * 2) if r["metadata"].get("date_modified", "") >= since.isoformat()][:top_k]

    def search_by_entity(self, entity: str, entity_type: str = "all", top_k: int = 8):
        entity_low = entity.lower()
        results = []
        for chunk in self.chunks:
            meta = chunk.as_metadata()
            fields = ["ner_persons", "ner_orgs", "ner_locations", "ner_misc"]
            if any(entity_low in (meta.get(field) or "").lower() for field in fields):
                results.append(self._to_result(chunk))
        return results[:top_k]


def _write_note(path: Path, title: str, body: str, tags: str = "python,data") -> None:
    path.write_text(
        f"---\ntitle: {title}\ntags: [{tags}]\n---\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.mark.integration
class TestCoreIntegration:
    def test_indexing_then_rag_query_returns_indexed_source(self, tmp_settings, mock_nlp):
        chroma = RecordingChroma()
        llm = MagicMock()
        llm.chat.return_value = "Réponse issue du coffre."

        note = tmp_settings.vault / "Python.md"
        _write_note(
            note,
            "Python pour data science",
            "Python est utilisé pour l'analyse de données. Pandas et scikit-learn sont centraux.",
        )

        with (
            patch("src.indexer.pipeline.settings", tmp_settings),
            patch("src.vault.parser.settings", tmp_settings),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
            patch("src.ai.rag.settings", tmp_settings),
        ):
            pipeline = IndexingPipeline(chroma)
            stats = pipeline.index_vault()
            rag = RAGPipeline(chroma=chroma, llm=llm)
            answer, sources = rag.query("Parle moi de Python pour data science")

        assert stats["added"] == 1
        assert chroma.count() > 0
        assert "Réponse issue du coffre." in answer
        assert "Aperçu" in answer
        assert sources
        assert sources[0]["metadata"]["note_title"] == "Python pour data science"

    def test_indexing_then_autolearn_processes_real_indexed_note(self, tmp_settings, mock_nlp):
        chroma = RecordingChroma()
        rag = MagicMock()
        rag.query.return_value = (
            "Réponse suffisamment longue pour être acceptée sans être considérée comme faible par le test.",
            [{"metadata": {"file_path": "Projet.md"}}],
        )
        rag._llm.chat.return_value = (
            "Réponse enrichie suffisamment longue pour être retenue comme une réponse forte dans le test d'intégration."
        )

        note = tmp_settings.vault / "Projet.md"
        _write_note(
            note,
            "Projet Alpha",
            "Le projet Alpha vise une croissance mesurable et documente plusieurs hypotheses de travail.",
            tags="projet,strategie",
        )

        with (
            patch("src.indexer.pipeline.settings", tmp_settings),
            patch("src.vault.parser.settings", tmp_settings),
            patch("src.vault.parser.get_nlp", return_value=mock_nlp),
            patch("src.learning.autolearn.settings", tmp_settings),
        ):
            pipeline = IndexingPipeline(chroma)
            pipeline.index_vault()
            learner = AutoLearner(chroma, rag, pipeline)
            note_meta = chroma.list_notes()[0]

            with (
                patch.object(learner, "_generate_questions", return_value=["Quelle progression recente ?"]),
                patch.object(learner, "_web_search", return_value=[]),
                patch.object(learner, "_is_weak_answer", return_value=False),
                patch.object(learner, "_save_knowledge_artifact") as save_artifact,
                patch.object(learner, "_set_status"),
            ):
                learner._process_note(note_meta, sleep_between_questions=0)

        save_artifact.assert_called_once()
        args = save_artifact.call_args.args
        assert args[0] == "Projet Alpha"
        assert args[1]["file_path"] == "Projet.md"
