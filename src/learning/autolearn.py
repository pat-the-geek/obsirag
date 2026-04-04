"""
Système d'auto-apprentissage en tâche de fond.

Cycle toutes les N minutes (configurable) :
1. Détecte les notes récemment modifiées
2. Pour chaque note : génère des questions via LLM et tente d'y répondre via RAG
3. Sauvegarde les artefacts de connaissance en Markdown dans obsirag/data/knowledge/
4. Apprend des requêtes utilisateur (stockées dans queries.jsonl)
5. Génère un rapport de synthèse hebdomadaire

CPU-friendly : pause entre chaque appel LLM, pas de parallélisme agressif.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from src.config import settings


_QUESTION_PROMPT = """Voici le contenu d'une note Obsidian :

---
{content}
---

Génère exactement 3 questions perspicaces sur ce contenu.
Les questions doivent explorer les idées clés, les connexions possibles ou les lacunes à approfondir.
Réponds UNIQUEMENT avec les 3 questions, une par ligne, sans numérotation ni explication."""

_WEEKLY_SYNTHESIS_PROMPT = """Tu es un assistant de synthèse pour un coffre Obsidian.
Voici les notes créées ou modifiées cette semaine :

{notes_summary}

Génère une synthèse structurée de la semaine en Markdown :
- Principaux thèmes abordés
- Connexions et patterns identifiés
- Points à approfondir
- Questions ouvertes
Sois concis et percutant (max 400 mots)."""


class AutoLearner:
    _SLEEP_BETWEEN_NOTES = 30        # secondes entre deux notes
    _SLEEP_BETWEEN_QUESTIONS = 15    # secondes entre deux questions

    def __init__(self, chroma, rag, indexer) -> None:
        self._chroma = chroma
        self._rag = rag
        self._indexer = indexer
        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone="UTC",
        )

    def start(self) -> None:
        interval = settings.autolearn_interval_minutes
        self._scheduler.add_job(
            self._run_cycle,
            "interval",
            minutes=interval,
            id="autolearn_cycle",
            next_run_time=datetime.utcnow() + timedelta(minutes=5),
        )
        # Synthèse hebdomadaire le dimanche à 20h UTC
        self._scheduler.add_job(
            self._weekly_synthesis,
            "cron",
            day_of_week="sun",
            hour=20,
            minute=0,
            id="weekly_synthesis",
        )
        self._scheduler.start()
        logger.info(f"Auto-learner démarré — cycle toutes les {interval} min")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def log_user_query(self, query: str) -> None:
        """Enregistre une requête utilisateur pour l'apprentissage futur."""
        entry = {"ts": datetime.utcnow().isoformat(), "query": query}
        f = settings.queries_file
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---- Cycle principal ----

    def _run_cycle(self) -> None:
        logger.info("Auto-learner : début du cycle")
        try:
            since = datetime.utcnow() - timedelta(hours=settings.autolearn_lookback_hours)
            recent = self._chroma.get_recently_modified(since)

            if not recent:
                logger.info("Auto-learner : aucune note récente")
                return

            processed = 0
            for note_meta in recent[: settings.autolearn_max_notes_per_run]:
                try:
                    self._process_note(note_meta)
                    processed += 1
                    time.sleep(self._SLEEP_BETWEEN_NOTES)
                except Exception as exc:
                    logger.warning(f"Auto-learner : erreur sur {note_meta['file_path']} : {exc}")

            logger.info(f"Auto-learner : {processed} note(s) traitée(s)")

        except Exception as exc:
            logger.error(f"Auto-learner cycle error : {exc}")

    def _process_note(self, note_meta: dict) -> None:
        title = note_meta.get("title", note_meta["file_path"])
        logger.debug(f"Auto-learner : traitement de '{title}'")

        chunks = self._chroma.search(title, top_k=5)
        if not chunks:
            return

        content_preview = "\n\n".join(c["text"] for c in chunks[:3])
        questions = self._generate_questions(content_preview)
        if not questions:
            return

        qa_pairs: list[dict] = []
        for question in questions:
            time.sleep(self._SLEEP_BETWEEN_QUESTIONS)
            try:
                answer, sources = self._rag.query(question)
                qa_pairs.append({
                    "question": question,
                    "answer": answer,
                    "sources": [s["metadata"].get("file_path", "") for s in sources[:3]],
                })
            except Exception as exc:
                logger.debug(f"Auto-learner QA failed : {exc}")

        if qa_pairs:
            self._save_knowledge_artifact(title, note_meta, qa_pairs)

    def _generate_questions(self, content: str) -> list[str]:
        try:
            prompt = _QUESTION_PROMPT.format(content=content[:3000])
            answer = self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300,
                operation="autolearn_questions",
            )
            lines = [l.strip().lstrip("•-0123456789.） ") for l in answer.strip().splitlines()]
            return [l for l in lines if len(l) > 10][:3]
        except Exception as exc:
            logger.debug(f"Génération de questions échouée : {exc}")
            return []

    def _save_knowledge_artifact(
        self,
        note_title: str,
        note_meta: dict,
        qa_pairs: list[dict],
    ) -> None:
        date_str = datetime.utcnow().strftime("%Y-%m")
        artifact_dir = settings.insights_dir / date_str
        artifact_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^\w\s-]", "", note_title).strip().replace(" ", "_")[:60]
        artifact_path = artifact_dir / f"{safe_name}_{datetime.utcnow().strftime('%Y%m%d')}.md"

        lines = [
            f"# Insights : {note_title}",
            "",
            f"**Source :** `{note_meta['file_path']}`  ",
            f"**Générée le :** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  ",
            f"**Tags source :** {note_meta.get('tags', [])}",
            "",
            "---",
            "",
        ]
        for i, qa in enumerate(qa_pairs, 1):
            lines += [
                f"## Question {i}",
                "",
                f"> {qa['question']}",
                "",
                qa["answer"],
                "",
                f"*Sources : {', '.join(f'`{s}`' for s in qa['sources'] if s)}*",
                "",
            ]

        artifact_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Artefact créé : {artifact_path.name}")

    # ---- Synthèse hebdomadaire ----

    def _weekly_synthesis(self) -> None:
        logger.info("Auto-learner : génération de la synthèse hebdomadaire")
        try:
            since = datetime.utcnow() - timedelta(days=7)
            recent = self._chroma.get_recently_modified(since)
            if not recent:
                return

            summary_lines = []
            for n in recent[:20]:
                chunks = self._chroma.search(n["title"], top_k=2)
                if chunks:
                    preview = chunks[0]["text"][:200]
                    summary_lines.append(f"- **{n['title']}** : {preview}…")

            prompt = _WEEKLY_SYNTHESIS_PROMPT.format(notes_summary="\n".join(summary_lines))
            synthesis = self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=600,
                operation="autolearn_synthesis",
            )

            week = datetime.utcnow().strftime("%Y-W%W")
            out_dir = settings.synthesis_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"semaine_{week}.md"
            header = (
                f"# Synthèse de la semaine {week}\n\n"
                f"*Générée automatiquement par ObsiRAG le "
                f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC*\n\n---\n\n"
            )
            out_path.write_text(header + synthesis, encoding="utf-8")
            logger.info(f"Synthèse hebdomadaire : {out_path.name}")

        except Exception as exc:
            logger.error(f"Synthèse hebdomadaire échouée : {exc}")
