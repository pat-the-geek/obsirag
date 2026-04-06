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
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from src.config import settings

# Mots-clés indiquant une réponse RAG insuffisante
_WEAK_ANSWER_PATTERNS = re.compile(
    r"je ne sais pas|pas d.information|pas mentionné|pas trouvé|"
    r"aucune information|impossible de répondre|don't know|no information|"
    r"not found|cannot answer|"
    # Variantes "je ne peux pas répondre"
    r"je ne peux pas (répondre|traiter|aborder|analyser|fournir|donner)|"
    r"il m.est (impossible|difficile) de (répondre|déterminer|évaluer|analyser)|"
    r"en me basant (uniquement |)sur (les extraits|les notes|le contexte|les documents)|"
    r"uniquement (sur|à partir d[eu]) (les |ces )?(extraits|notes|documents|informations) (fourni|disponible|présent)|"
    r"aucune? (critique|mention|référence|donnée|détail|élément|source|réponse|note|information|résultat|contenu|extrait|passage|texte|document|analyse|explication|précision|contexte|indice|lien|connexion|rapport|étude|exemple|preuve|argument|base|fondement|indication|trace|occurrence|cas|fait|observation|constat|insight|réponse spécifique)|"
    r"n.a pas (été|pu|trouvé|mentionné|abordé|traité|évoqué|discuté|inclus|précisé|détaillé|expliqué|analysé)|"
    r"les (extraits?|notes?|documents?|textes?) (ne |n.)(contiennent?|mentionnent?|incluent?|précisent?|détaillent?|abordent?|traitent?|évoquent?|discutent?|fournissent?|donnent?|parlent?|font? (pas )?mention)|"
    r"se concentre(nt)? (plutôt|davantage)|"
    r"insuffisant|manque d.information|hors de (ma |mon |notre )|(au-delà|en dehors) (du |de la |des )?contexte|"
    r"aucun (des |de ces |ces )?documents? (ne |n.)|"
    r"les extraits (fournis|consultés|disponibles)|"
    r"ne (décri(t|vent)|fournit|précise|détaille|mentionne|aborde|traite|évoque|donne|contient|inclut|présente|explique|analyse)(nt)? pas|"
    r"il n.y a (pas|aucun)|"
    r"je ne trouve (pas|aucune?)|"
    r"context(e)? ne (fournit|donne|contient|précise|inclut|mentionne)|"
    r"notes (consultées|fournis) (indiquent|précisent|mentionnent).{0,80}(aucun|pas|ne )|"
    # Variantes "extraits/notes fournis ne contiennent pas/aucune information"
    r"(extraits?|notes?) (de notes? )?fourni[se]? ne contiennent? (pas|aucune?)|"
    r"(extraits?|notes?) fourni[se]? ne contiennent? pas (d.études?|de données?|d.informations?)|"
    # "je ne peux pas répondre de manière exhaustive"
    r"je ne peux pas (répondre|traiter|aborder|analyser|fournir) de manière exhaustive|"
    r"de manière exhaustive (à votre question|car)|"
    # "ni de données précises" / "ni d'études récentes"
    r"ni de (données? précises?|études? récentes?|informations? (précises?|suffisantes?))|"
    # "ne contiennent pas d'études/données"
    r"ne contiennent? pas (d.études?|de données? (précises?|récentes?|comparatives?)|d.informations? (sur|concernant|relatives?))|"
    # "répondre de façon exhaustive / complète"
    r"(répondre|traiter|aborder).{0,30}(de façon|de manière) (exhaustive|complète|précise) (à |sur )?(cette|votre|la )?question",
    re.IGNORECASE,
)
_MIN_ANSWER_LENGTH = 150  # réponse trop courte = insuffisante


_SEMANTIC_FIELD_PROMPT = """<contenu>
{content}
</contenu>

Identifie le champ sémantique de ce contenu. Réponds UNIQUEMENT avec cette ligne au format exact :
"Domaine: [domaine principal] | Concepts: [concept1, concept2, concept3] | Angle: [angle spécifique traité]"
Rien d'autre."""

_QUESTION_PROMPT = """<champ_semantique>
{semantic_field}
</champ_semantique>

<contenu>
{content}
</contenu>

En te basant STRICTEMENT sur ce champ sémantique et ce contenu, génère 3 questions en français pour approfondir CE SUJET PRÉCIS avec des données externes récentes (chiffres, études, comparaisons, impacts mesurables, évolutions). Chaque question doit rester alignée avec le domaine et les concepts identifiés dans le champ sémantique. Une par ligne, rien d'autre.
Q1:
Q2:
Q3:"""

_WEB_ANSWER_PROMPT = """Question : {question}

Contexte depuis mes notes personnelles :
{rag_context}

Sources web trouvées :
{web_context}

Rédige une réponse enrichie en français qui apporte de la CONNAISSANCE NOUVELLE par rapport au contexte de mes notes. Appuie-toi sur les sources web pour ajouter des faits, chiffres, études ou exemples concrets. Sois structuré et précis."""

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
    _USER_IDLE_SECONDS = 120         # pause auto-learner si activité chat < N secondes

    def __init__(self, chroma, rag, indexer) -> None:
        self._chroma = chroma
        self._rag = rag
        self._indexer = indexer
        self._last_user_activity: float = 0.0  # timestamp epoch
        self._activity_lock = threading.Lock()
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

    def signal_user_activity(self) -> None:
        """Signale une activité utilisateur — suspend temporairement l'auto-learner."""
        with self._activity_lock:
            self._last_user_activity = time.monotonic()

    def _user_is_active(self) -> bool:
        """Retourne True si l'utilisateur a été actif dans les dernières N secondes."""
        with self._activity_lock:
            return (time.monotonic() - self._last_user_activity) < self._USER_IDLE_SECONDS

    def _wait_for_idle(self, context: str = "") -> None:
        """Attend que l'utilisateur soit inactif avant de continuer."""
        if not self._user_is_active():
            return
        label = f" ({context})" if context else ""
        logger.info(f"Auto-learner en pause{label} — activité chat détectée, reprise dans {self._USER_IDLE_SECONDS}s max")
        while self._user_is_active():
            time.sleep(10)
        logger.info(f"Auto-learner reprise{label}")

    def log_user_query(self, query: str) -> None:
        """Enregistre une requête utilisateur et signale l'activité."""
        self.signal_user_activity()
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
                self._wait_for_idle(note_meta.get("title", ""))
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
                self._wait_for_idle(note_meta.get("title", ""))
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
        semantic_field = self._extract_semantic_field(content_preview)
        time.sleep(5)
        questions = self._generate_questions(content_preview, semantic_field)
        if not questions:
            logger.warning(f"Auto-learner : aucune question générée pour '{title}'")
            return

        logger.info(f"Auto-learner : {len(questions)} question(s) générée(s) pour '{title}'")
        qa_pairs: list[dict] = []
        for question in questions:
            time.sleep(self._SLEEP_BETWEEN_QUESTIONS)
            try:
                # 1. Web en premier — source principale de connaissance nouvelle
                web_results = self._web_search(question)
                web_snippets = [r["body"] for r in web_results if r.get("body")]

                # 2. RAG pour contexte personnel (secondaire)
                _, sources = self._rag.query(question)
                rag_context = "\n\n".join(
                    c.get("text", "")[:400] for c in sources[:2]
                ) if sources else "Aucune note personnelle sur ce sujet."

                # 3. Synthèse : web + contexte coffre
                if web_snippets and self._snippets_relevant(question, web_snippets):
                    web_context = "\n\n".join(web_snippets[:3])
                    prompt = _WEB_ANSWER_PROMPT.format(
                        question=question,
                        rag_context=rag_context[:800],
                        web_context=web_context,
                    )
                    try:
                        answer = self._rag._llm.chat(
                            [{"role": "user", "content": prompt}],
                            temperature=0.3,
                            max_tokens=4096,
                            operation="autolearn_enrich",
                        )
                        provenance = "Web + Coffre" if sources else "Web"
                        logger.info(f"Auto-learner : réponse web pour '{question[:60]}'")
                    except Exception:
                        # Fallback LLM échoué → RAG seul, pas de snippets bruts
                        answer, sources = self._rag.query(question)
                        web_results = []
                        provenance = "Coffre"
                else:
                    # Fallback : réponse RAG seule
                    answer, sources = self._rag.query(question)
                    web_results = []
                    provenance = "Coffre"

                # Rejeter les réponses faibles ou génériques
                if self._is_weak_answer(answer):
                    logger.debug(f"Réponse faible ignorée pour '{question[:60]}'")
                    continue

                qa_pairs.append({
                    "question": question,
                    "answer": answer,
                    "sources": [s["metadata"].get("file_path", "") for s in sources[:3]],
                    "web_refs": [{"title": r.get("title", r.get("href", "")), "url": r.get("href", "")} for r in web_results],
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

    @staticmethod
    def _fetch_url_content(url: str, max_chars: int = 3000) -> str:
        """Fetche le contenu textuel d'une URL. Retourne une chaîne vide en cas d'échec."""
        # Ignorer les PDFs — texte extrait sans espaces, inutilisable
        if url.lower().endswith(".pdf") or "/pdf" in url.lower():
            logger.debug(f"URL PDF ignorée : {url[:60]}")
            return ""
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "pdf" in content_type.lower():
                    return ""
                raw = resp.read(50_000).decode("utf-8", errors="ignore")
            # Extraction texte brut : supprimer balises HTML
            text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            # Réparer les mots collés : insérer espace avant une majuscule précédée d'une minuscule
            text = re.sub(r"([a-zàéèêëîïôùûüç])([A-ZÀÉÈÊËÎÏÔÙÛÜÇ])", r"\1 \2", text)
            text = re.sub(r"\s+", " ", text).strip()
            # Rejeter si trop de mots collés :
            # 1. Ratio espaces/chars trop bas
            if len(text) > 100 and text.count(" ") / len(text) < 0.05:
                return ""
            # 2. Trop de "mots" très longs (>15 chars) = mots collés sans majuscule
            words = text.split()
            if words:
                long_words = sum(1 for w in words if len(w) > 15 and w.isalpha())
                if long_words / len(words) > 0.15:
                    return ""
            return text[:max_chars]
        except Exception:
            return ""

    def _synthesize_web_sources(self, note_title: str, qa_pairs: list[dict]) -> str:
        """Fetche et synthétise le contenu des URLs citées dans les Q&A."""
        all_refs: list[dict] = []
        seen_urls: set[str] = set()
        for qa in qa_pairs:
            for ref in qa.get("web_refs", []):
                url = ref.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_refs.append(ref)

        if not all_refs:
            return ""

        fetched: list[str] = []
        for ref in all_refs[:4]:  # max 4 URLs
            content = self._fetch_url_content(ref["url"])
            if content:
                fetched.append(f"### {ref.get('title', ref['url'])}\n{content}")
                logger.debug(f"Fetché : {ref['url'][:60]}")

        if not fetched:
            return ""

        combined = "\n\n".join(fetched)
        prompt = (
            f"Sujet : {note_title}\n\n"
            f"Voici le contenu de {len(fetched)} source(s) web citées dans les insights :\n\n"
            f"{combined}\n\n"
            f"Rédige une synthèse structurée en français (max 400 mots) qui extrait "
            f"les informations clés, faits importants et apports de connaissance de ces sources. "
            f"Format : paragraphes courts avec sous-titres Markdown si pertinent."
        )
        try:
            return self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
                operation="autolearn_web_synthesis",
            )
        except Exception as exc:
            logger.debug(f"Synthèse sources web échouée : {exc}")
            return ""

    def _web_search(self, query: str) -> list[dict]:
        """Retourne une liste de {body, href, title} filtrée sur les domaines fiables."""
        try:
            from ddgs import DDGS
            # Enrichir la requête pour orienter vers du contenu académique/informatif
            enriched_query = f"{query} explication analyse histoire contexte"
            with DDGS() as ddgs:
                results = list(ddgs.text(enriched_query, max_results=15))
            trusted = [
                r for r in results
                if any(d in r.get("href", "") for d in self._TRUSTED_DOMAINS)
            ]
            selected = trusted[:3] if trusted else results[:3]
            return [r for r in selected if r.get("body")]
        except Exception as exc:
            logger.debug(f"Web search échouée : {exc}")
            return []

    @staticmethod
    def _snippets_relevant(question: str, snippets: list[str]) -> bool:
        """Vérifie que les snippets web contiennent au moins un mot-clé de la question."""
        words = [w.lower() for w in re.findall(r"\b\w{5,}\b", question)]
        if not words or not snippets:
            return bool(snippets)
        combined = " ".join(snippets).lower()
        # Seuil très bas : 1 seul mot suffit pour considérer les snippets pertinents
        return any(w in combined for w in words)

    def _enrich_with_web(self, question: str, rag_answer: str, web_snippets: list[str]) -> str:
        # Vérifier la pertinence des sources avant d'enrichir
        if not self._snippets_relevant(question, web_snippets):
            logger.debug(f"Sources web hors sujet pour : {question[:60]}")
            return rag_answer

        context = "\n\n".join(web_snippets[:3])
        prompt = (
            f"Question : {question}\n\n"
            f"Sources web :\n{context}\n\n"
            f"Rédige une réponse structurée et informative en français, en t'appuyant principalement "
            f"sur les sources web ci-dessus. Apporte des faits concrets, des chiffres, des exemples "
            f"et du contexte qui enrichissent la compréhension du sujet. Sois précis et complet."
        )
        try:
            return self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4096,
                operation="autolearn_enrich",
            )
        except Exception as exc:
            logger.debug(f"Enrichissement web échoué : {exc}")
            return rag_answer

    def _extract_semantic_field(self, content: str) -> str:
        """Détermine le champ sémantique du contenu pour contraindre la génération de questions."""
        try:
            prompt = _SEMANTIC_FIELD_PROMPT.format(content=content[:2000])
            result = self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=150,
                operation="autolearn_semantic_field",
            )
            field = result.strip().strip('"')
            logger.debug(f"Champ sémantique détecté : {field[:120]}")
            return field
        except Exception as exc:
            logger.debug(f"Extraction du champ sémantique échouée : {exc}")
            return ""

    def _generate_questions(self, content: str, semantic_field: str = "") -> list[str]:
        try:
            prompt = _QUESTION_PROMPT.format(
                content=content[:3000],
                semantic_field=semantic_field or "Non déterminé",
            )
            answer = self._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000,
                operation="autolearn_questions",
            )
            _prefix = re.compile(r"^[•\*\-]?\s*(?:Q\d+[.:）]|Question\s*\d*[.:]|\d+[.)]\s*)?\s*", re.I)
            questions: list[str] = []
            for line in answer.strip().splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                cleaned = _prefix.sub("", stripped).strip()
                if len(cleaned) > 10 and cleaned.endswith("?"):
                    questions.append(cleaned)
            return questions[:3]
        except Exception as exc:
            logger.debug(f"Génération de questions échouée : {exc}")
            return []

    @staticmethod
    def _entities_to_tags(text: str) -> list[str]:
        """Extrait les entités NER du texte et les convertit en tags Obsidian."""
        try:
            from src.vault.parser import get_nlp
            nlp = get_nlp()
            doc = nlp(text[:10_000])
            tags: list[str] = []
            seen: set[str] = set()
            for ent in doc.ents:
                value = ent.text.strip()
                if not value or len(value) < 3:
                    continue
                label = ent.label_
                if label == "PER":
                    prefix = "personne"
                elif label == "ORG":
                    prefix = "org"
                elif label in ("LOC", "GPE"):
                    prefix = "lieu"
                else:
                    continue  # ignorer les entités MISC pour les tags
                # Normalise : minuscules, supprime accents, remplace espaces par -
                slug = unicodedata.normalize("NFD", value.lower())
                slug = "".join(c for c in slug if unicodedata.category(c) != "Mn")
                slug = re.sub(r"[^\w\s-]", "", slug).strip()
                slug = re.sub(r"[\s_]+", "-", slug)
                tag = f"{prefix}/{slug}"
                if tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
            return tags[:20]
        except Exception:
            return []

    # ---- Helpers frontmatter ----

    @staticmethod
    def _read_frontmatter_tags(content: str) -> list[str]:
        """Extrait les tags du frontmatter YAML d'un fichier Markdown."""
        if not content.startswith("---"):
            return []
        end = content.find("---", 3)
        if end == -1:
            return []
        tags: list[str] = []
        in_tags = False
        for line in content[3:end].splitlines():
            if re.match(r"^tags\s*:", line):
                in_tags = True
                continue
            if in_tags:
                m = re.match(r"\s+-\s+(.+)", line)
                if m:
                    tags.append(m.group(1).strip())
                elif line.strip() and not line.startswith(" "):
                    in_tags = False
        return tags

    @staticmethod
    def _merge_frontmatter_tags(content: str, new_tags: list[str]) -> str:
        """Ajoute de nouveaux tags au frontmatter YAML sans doublons."""
        existing = AutoLearner._read_frontmatter_tags(content)
        merged = list(existing)
        for t in new_tags:
            if t not in merged:
                merged.append(t)
        if not content.startswith("---"):
            fm = "---\ntags:\n" + "\n".join(f"  - {t}" for t in merged) + "\n---\n"
            return fm + content
        end = content.find("---", 3)
        if end == -1:
            return content
        fm = "---\ntags:\n" + "\n".join(f"  - {t}" for t in merged) + "\n---"
        return fm + content[end + 3:]

    # ---- Recherche et mise à jour d'artefacts existants ----

    def _find_existing_insight(self, note_title: str, ner_tags: list[str]) -> Path | None:
        """Cherche un artefact insight existant par titre de note ou overlap NER.

        Critères (par ordre de priorité) :
        1. Le stem du fichier commence par safe_name (même note)
        2. ≥ 2 tags NER en commun (même thématique)
        Retourne le chemin du fichier le plus pertinent, ou None.
        """
        insights_root = settings.insights_dir
        if not insights_root.exists():
            return None

        safe_name = re.sub(r"[^\w\s-]", "", note_title).strip().replace(" ", "_")[:60].lower()
        new_ner_set = {t for t in ner_tags if "/" in t}

        best_path: Path | None = None
        best_score = 0

        for path in insights_root.rglob("*.md"):
            score = 0
            # Critère 1 : titre
            if path.stem.lower().startswith(safe_name):
                score += 10
            # Critère 2 : overlap NER via frontmatter
            if new_ner_set:
                try:
                    existing_tags = self._read_frontmatter_tags(
                        path.read_text(encoding="utf-8")
                    )
                    existing_ner = {t for t in existing_tags if "/" in t}
                    overlap = len(new_ner_set & existing_ner)
                    if overlap >= 2:
                        score += overlap * 2
                except Exception:
                    pass
            if score > best_score:
                best_score = score
                best_path = path

        # Seuil minimal : au moins un critère fort (titre = 10, NER ≥ 2 → score ≥ 4)
        return best_path if best_score >= 4 else None

    def _append_to_insight(
        self,
        path: Path,
        qa_pairs: list[dict],
        ner_tags: list[str],
        provenance: str,
    ) -> None:
        """Appende de nouveaux Q&A à un artefact existant et met à jour ses tags NER."""
        content = path.read_text(encoding="utf-8")

        # Numérotation : compter les ## Question N existants
        existing_count = len(re.findall(r"^## Question \d+", content, re.MULTILINE))

        # Fusionner les nouveaux tags NER dans le frontmatter
        content = self._merge_frontmatter_tags(content, ner_tags)

        # Mettre à jour la ligne "Générée le" → "Mise à jour le"
        content = re.sub(
            r"\*\*(Générée|Mise à jour) le :\*\*.*",
            f"**Mise à jour le :** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  ",
            content,
        )

        def _wikilink(fp: str) -> str:
            return f"[[{fp.removesuffix('.md')}]]"

        new_lines: list[str] = [""]
        for i, qa in enumerate(qa_pairs, existing_count + 1):
            provenance_label = qa.get("provenance", provenance)
            source_links = ", ".join(_wikilink(s) for s in qa["sources"] if s)
            new_lines += [
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

        # Synthèse des sources web fetchées
        note_title = path.stem
        web_synthesis = self._synthesize_web_sources(note_title, qa_pairs)
        if web_synthesis:
            new_lines += [
                "---",
                "",
                "## Synthèse des sources web",
                "",
                web_synthesis,
                "",
            ]

        path.write_text(content.rstrip() + "\n" + "\n".join(new_lines), encoding="utf-8")
        logger.info(
            f"Artefact mis à jour : {path.name} "
            f"(+{len(qa_pairs)} Q&A → total {existing_count + len(qa_pairs)})"
        )

    # ---- Sauvegarde / création d'artefact ----

    def _save_knowledge_artifact(
        self,
        note_title: str,
        note_meta: dict,
        qa_pairs: list[dict],
    ) -> None:
        # Provenance globale
        provenances = {qa.get("provenance", "Coffre") for qa in qa_pairs}
        if "Coffre et Web" in provenances or ("Coffre" in provenances and "Web" in provenances):
            global_provenance = "Coffre et Web"
        elif "Web" in provenances:
            global_provenance = "Web"
        else:
            global_provenance = "Coffre"

        def _wikilink(fp: str) -> str:
            return f"[[{fp.removesuffix('.md')}]]"

        # Extraction NER sur le contenu QA
        qa_text = " ".join(qa["question"] + " " + qa["answer"] for qa in qa_pairs)
        ner_tags = self._entities_to_tags(qa_text)
        source_tags = [t for t in note_meta.get("tags", []) if t]

        # ---- Vérifier si un artefact existant peut être complété ----
        existing = self._find_existing_insight(note_title, ner_tags)
        if existing:
            self._append_to_insight(existing, qa_pairs, ner_tags, global_provenance)
            return

        # ---- Création d'un nouvel artefact ----
        date_str = datetime.utcnow().strftime("%Y-%m")
        artifact_dir = settings.insights_dir / date_str
        artifact_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^\w\s-]", "", note_title).strip().replace(" ", "_")[:60]
        artifact_path = artifact_dir / f"{safe_name}_{datetime.utcnow().strftime('%Y%m%d')}.md"

        all_tags = ["insight"] + source_tags + ner_tags
        fm_tags = "\n".join(f"  - {t}" for t in all_tags)
        frontmatter = f"---\ntags:\n{fm_tags}\n---\n"

        source_link = _wikilink(note_meta["file_path"])
        lines = [
            frontmatter,
            f"# Insights : {note_title}",
            "",
            f"**Note source :** {source_link}  ",
            f"**Générée le :** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC  ",
            f"**Tags source :** {source_tags}  ",
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

        # Synthèse des sources web fetchées
        web_synthesis = self._synthesize_web_sources(note_title, qa_pairs)
        if web_synthesis:
            lines += [
                "---",
                "",
                "## Synthèse des sources web",
                "",
                web_synthesis,
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
            max_tokens=1024,
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
                max_tokens=2048,
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
