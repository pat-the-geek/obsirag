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

# Mots-clés indiquant une réponse RAG insuffisante
_WEAK_ANSWER_PATTERNS = re.compile(
    r"je ne sais pas|pas d.information|pas mentionné|pas trouvé|"
    r"aucune information|impossible de répondre|don't know|no information|"
    r"not found|cannot answer",
    re.IGNORECASE,
)
_MIN_ANSWER_LENGTH = 150  # réponse trop courte = insuffisante


_QUESTION_PROMPT = """<contenu>
{content}
</contenu>

Génère exactement 3 questions en français sur ce contenu, une par ligne, rien d'autre.
Q1:
Q2:
Q3:"""

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

    # ---- Suivi des notes traitées ----

    def _load_processed(self) -> dict[str, str]:
        """Retourne {file_path: last_processed_iso}."""
        f = settings.processed_notes_file
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_processed(self, processed: dict[str, str]) -> None:
        f = settings.processed_notes_file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")

    def _mark_processed(self, file_path: str) -> None:
        processed = self._load_processed()
        processed[file_path] = datetime.utcnow().isoformat()
        self._save_processed(processed)

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
            processed_count = 0
            processed_map = self._load_processed()

            # Pass 1 — notes récemment modifiées
            since = datetime.utcnow() - timedelta(hours=settings.autolearn_lookback_hours)
            recent = self._chroma.get_recently_modified(since)
            for note_meta in recent[: settings.autolearn_max_notes_per_run]:
                try:
                    self._process_note(note_meta)
                    self._mark_processed(note_meta["file_path"])
                    processed_count += 1
                    time.sleep(self._SLEEP_BETWEEN_NOTES)
                except Exception as exc:
                    logger.warning(f"Auto-learner : erreur sur {note_meta['file_path']} : {exc}")

            # Pass 2 — full-scan progressif : notes jamais traitées ou les plus anciennes
            all_notes = self._chroma.list_notes()
            # Trie : jamais traitées d'abord, puis par date de traitement croissante
            def _sort_key(n: dict) -> str:
                return processed_map.get(n["file_path"], "")  # "" < toute date ISO

            pending = sorted(all_notes, key=_sort_key)
            quota = settings.autolearn_fullscan_per_run
            for note_meta in pending:
                if quota <= 0:
                    break
                fp = note_meta["file_path"]
                # Sauter les notes déjà traitées dans ce cycle (pass 1)
                if fp in {n["file_path"] for n in recent[: settings.autolearn_max_notes_per_run]}:
                    continue
                try:
                    self._process_note(note_meta)
                    self._mark_processed(fp)
                    processed_count += 1
                    quota -= 1
                    time.sleep(self._SLEEP_BETWEEN_NOTES)
                except Exception as exc:
                    logger.warning(f"Auto-learner full-scan : erreur sur {fp} : {exc}")

            logger.info(f"Auto-learner : {processed_count} note(s) traitée(s)")

            # Pass 3 — découverte de synapses (connexions implicites)
            self._discover_synapses(all_notes)

        except Exception as exc:
            logger.error(f"Auto-learner cycle error : {exc}")

    def _process_note(self, note_meta: dict) -> None:
        title = note_meta.get("title", note_meta["file_path"])
        logger.info(f"Auto-learner : traitement de '{title}'")

        chunks = self._chroma.search(title, top_k=5)
        if not chunks:
            logger.warning(f"Auto-learner : aucun chunk trouvé pour '{title}'")
            return

        content_preview = "\n\n".join(c["text"] for c in chunks[:3])
        questions = self._generate_questions(content_preview)
        if not questions:
            logger.warning(f"Auto-learner : aucune question générée pour '{title}'")
            return

        logger.info(f"Auto-learner : {len(questions)} question(s) générée(s) pour '{title}'")
        qa_pairs: list[dict] = []
        for question in questions:
            time.sleep(self._SLEEP_BETWEEN_QUESTIONS)
            try:
                answer, sources = self._rag.query(question)
                web_results: list[dict] = []

                # Compléter avec le web si la réponse RAG est insuffisante
                if self._is_weak_answer(answer):
                    web_results = self._web_search(question)
                    if web_results:
                        snippets = [r["body"] for r in web_results]
                        answer = self._enrich_with_web(question, answer, snippets)
                        logger.info(f"Auto-learner : réponse enrichie via web pour '{question[:60]}'")

                provenance = "Coffre"
                if web_results and sources:
                    provenance = "Coffre et Web"
                elif web_results:
                    provenance = "Web"

                qa_pairs.append({
                    "question": question,
                    "answer": answer,
                    "sources": [s["metadata"].get("file_path", "") for s in sources[:3]],
                    "web_refs": [{"title": r.get("title", r["href"]), "url": r["href"]} for r in web_results],
                    "provenance": provenance,
                })
            except Exception as exc:
                logger.warning(f"Auto-learner QA failed pour '{title}' : {exc}")

        if qa_pairs:
            self._save_knowledge_artifact(title, note_meta, qa_pairs)
        else:
            logger.warning(f"Auto-learner : aucune réponse QA pour '{title}', artefact non créé")

    def _is_weak_answer(self, answer: str) -> bool:
        return len(answer.strip()) < _MIN_ANSWER_LENGTH or bool(_WEAK_ANSWER_PATTERNS.search(answer))

    # Domaines considérés comme fiables
    _TRUSTED_DOMAINS = {
        "wikipedia.org", "wikimedia.org",
        "nature.com", "science.org", "pubmed.ncbi.nlm.nih.gov", "arxiv.org",
        "gouv.fr", "europa.eu", "who.int", "un.org",
        "mit.edu", "stanford.edu", "harvard.edu",
        "lemonde.fr", "lefigaro.fr", "liberation.fr", "letemps.ch",
        "bbc.com", "reuters.com", "apnews.com", "theguardian.com",
        "economist.com", "hbr.org",
        "python.org", "docs.python.org", "developer.mozilla.org",
    }

    def _web_search(self, query: str) -> list[dict]:
        """Retourne une liste de {body, href, title} filtrée sur les domaines fiables."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=10))
            trusted = [
                r for r in results
                if any(d in r.get("href", "") for d in self._TRUSTED_DOMAINS)
            ]
            selected = trusted[:3] if trusted else results[:3]
            return [r for r in selected if r.get("body")]
        except Exception as exc:
            logger.debug(f"Web search échouée : {exc}")
            return []

    def _enrich_with_web(self, question: str, rag_answer: str, web_snippets: list[str]) -> str:
        context = "\n\n".join(web_snippets[:3])
        prompt = (
            f"Question : {question}\n\n"
            f"Réponse partielle depuis le coffre de notes :\n{rag_answer}\n\n"
            f"Informations complémentaires trouvées sur le web :\n{context}\n\n"
            f"Synthétise une réponse complète et concise en intégrant les deux sources. "
            f"Réponds uniquement en français."
        )
        try:
            return self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
                operation="autolearn_enrich",
            )
        except Exception as exc:
            logger.debug(f"Enrichissement web échoué : {exc}")
            return rag_answer

    def _generate_questions(self, content: str) -> list[str]:
        try:
            prompt = _QUESTION_PROMPT.format(content=content[:3000])
            answer = self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=600,
                operation="autolearn_questions",
            )
            lines = [re.sub(r"^[•\-]?\s*Q\d+[.:）]\s*", "", l.strip()) for l in answer.strip().splitlines()]
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

        # Provenance globale de l'artefact
        provenances = {qa.get("provenance", "Coffre") for qa in qa_pairs}
        if "Coffre et Web" in provenances or ("Coffre" in provenances and "Web" in provenances):
            global_provenance = "Coffre et Web"
        elif "Web" in provenances:
            global_provenance = "Web"
        else:
            global_provenance = "Coffre"

        def _wikilink(fp: str) -> str:
            """Convertit un chemin de fichier en wikilink Obsidian cliquable."""
            return f"[[{fp.removesuffix('.md')}]]"

        source_link = _wikilink(note_meta["file_path"])
        lines = [
            f"# Insights : {note_title}",
            "",
            f"**Note source :** {source_link}  ",
            f"**Générée le :** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  ",
            f"**Tags source :** {note_meta.get('tags', [])}  ",
            f"**Provenance :** {global_provenance}",
            "",
            "---",
            "",
        ]
        for i, qa in enumerate(qa_pairs, 1):
            provenance_label = qa.get("provenance", "Coffre")
            source_links = ", ".join(_wikilink(s) for s in qa["sources"] if s)
            lines += [
                f"## Question {i}",
                "",
                f"> {qa['question']}",
                "",
                qa["answer"],
                "",
                f"*Provenance : {provenance_label}*  ",
                f"*Notes consultées : {source_links}*  " if source_links else "",
                *([f"*Références web :*"] + [f"- [{r['title']}]({r['url']})" for r in qa.get("web_refs", [])] if qa.get("web_refs") else []),
                "",
            ]

        artifact_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Artefact créé : {artifact_path.name}")

    # ---- Découverte de synapses ----

    def _load_synapse_index(self) -> set[str]:
        """Retourne l'ensemble des paires déjà traitées sous forme 'fp_a|||fp_b'."""
        f = settings.synapse_index_file
        if f.exists():
            try:
                return set(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def _save_synapse_index(self, index: set[str]) -> None:
        f = settings.synapse_index_file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(sorted(index), ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _synapse_pair_key(fp_a: str, fp_b: str) -> str:
        return "|||".join(sorted([fp_a, fp_b]))

    def _discover_synapses(self, all_notes: list[dict]) -> None:
        """Trouve des paires de notes sémantiquement proches sans lien existant."""
        quota = settings.autolearn_synapse_per_run
        if quota <= 0:
            return

        synapse_index = self._load_synapse_index()

        # On itère sur les notes dans un ordre aléatoire pour couvrir tout le coffre
        import random
        candidates = list(all_notes)
        random.shuffle(candidates)

        for note_a in candidates:
            if quota <= 0:
                break
            fp_a = note_a["file_path"]
            # Liens existants (wikilinks déjà connus)
            existing = {w.lower() for w in note_a.get("wikilinks", [])}

            similar = self._chroma.find_similar_notes(
                source_fp=fp_a,
                existing_links=existing,
                top_k=5,
                threshold=settings.autolearn_synapse_threshold,
            )

            for note_b_info in similar:
                if quota <= 0:
                    break
                fp_b = note_b_info["file_path"]
                pair_key = self._synapse_pair_key(fp_a, fp_b)
                if pair_key in synapse_index:
                    continue

                try:
                    self._create_synapse_artifact(note_a, note_b_info)
                    synapse_index.add(pair_key)
                    self._save_synapse_index(synapse_index)
                    quota -= 1
                    time.sleep(self._SLEEP_BETWEEN_QUESTIONS)
                except Exception as exc:
                    logger.warning(f"Synapse {fp_a} ↔ {fp_b} : {exc}")

    def _create_synapse_artifact(self, note_a: dict, note_b_info: dict) -> None:
        title_a = note_a.get("title", note_a["file_path"])
        title_b = note_b_info["title"]
        score = note_b_info["score"]
        excerpt_b = note_b_info["excerpt"]

        # Récupère un extrait de note_a
        chunks_a = self._chroma.search(title_a, top_k=1)
        excerpt_a = chunks_a[0]["text"][:300] if chunks_a else ""

        prompt = (
            f"Voici deux notes d'un coffre Obsidian qui semblent liées thématiquement "
            f"(similarité sémantique : {score:.0%}) mais sans lien explicite entre elles.\n\n"
            f"**Note A — {title_a} :**\n{excerpt_a}\n\n"
            f"**Note B — {title_b} :**\n{excerpt_b}\n\n"
            f"En 3 à 5 phrases, explique quelle connexion implicite unit ces deux notes, "
            f"comme une synapse qui relie deux neurones. Propose aussi une question que "
            f"l'utilisateur pourrait se poser pour approfondir ce lien. Réponds en français."
        )

        explanation = self._rag._llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=400,
            operation="autolearn_synapse",
        )

        safe_a = re.sub(r"[^\w\s-]", "", title_a).strip().replace(" ", "_")[:40]
        safe_b = re.sub(r"[^\w\s-]", "", title_b).strip().replace(" ", "_")[:40]
        date_str = datetime.utcnow().strftime("%Y%m%d")
        out_dir = settings.synapses_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{safe_a}__{safe_b}_{date_str}.md"

        lines = [
            f"# Synapse : {title_a} ↔ {title_b}",
            "",
            f"**Similarité sémantique :** {score:.0%}  ",
            f"**Découverte le :** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
            "",
            "---",
            "",
            "## Connexion identifiée",
            "",
            explanation,
            "",
            "---",
            "",
            f"## [[{title_a}]]",
            "",
            f"> {excerpt_a[:250]}…",
            "",
            f"## [[{title_b}]]",
            "",
            f"> {excerpt_b[:250]}…",
        ]
        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Synapse créée : {title_a} ↔ {title_b} ({score:.0%})")

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
