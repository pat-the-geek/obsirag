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
import os
import re
import tempfile
import threading
import time
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from src.config import settings
from src.learning.artifact_writer import AutoLearnArtifactWriter
from src.learning.entity_services import AutoLearnEntityServices
from src.learning.note_renamer import AutoLearnNoteRenamer
from src.learning.question_answering import AutoLearnQuestionAnswering
from src.learning.synapse_discovery import AutoLearnSynapseDiscovery
from src.learning.web_enrichment import AutoLearnWebEnrichment
from src.metrics import MetricsRecorder
from src.storage.json_state import JsonStateStore

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

# Mapping type WUDD.ai → préfixe de tag Obsidian
_WUDDAI_TYPE_TO_PREFIX: dict[str, str] = {
    "PERSON":  "personne",
    "ORG":     "org",
    "GPE":     "lieu",
    "LOC":     "lieu",
    "PRODUCT": "produit",
    "EVENT":   "event",
    "NORP":    "groupe",
    "FAC":     "lieu",
}

# Types affichés dans la galerie d'images des insights (ordre de priorité)
_WUDDAI_IMAGE_TYPES = ["PERSON", "ORG", "GPE", "PRODUCT"]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _utc_now_naive() -> datetime:
    return _utc_now().replace(tzinfo=None)


def _normalize_entity_name(text: str) -> str:
    """Normalise un nom d'entité pour la comparaison (minuscules, sans accents)."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


_QUESTION_PROMPT = """<contenu>
{content}
</contenu>
{already_asked_section}
Analyse ce contenu et génère UNE SEULE question en français, la plus pertinente pour approfondir ce sujet précis avec des données externes récentes (chiffres, études, comparaisons, impacts mesurables, évolutions). La question doit être ancrée dans le domaine principal du contenu et cibler un fait mesurable ou une évolution récente. Réponds UNIQUEMENT avec la question, rien d'autre."""

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

_QUESTION_PREFIX_RE = re.compile(r"^[•\*\-]?\s*(?:Q\d+[.:）]|Question\s*\d*[.:]|\d+[.)]\s*)?\s*", re.I)


class AutoLearner:
    _SLEEP_BETWEEN_NOTES = 30        # secondes entre deux notes
    _SLEEP_BETWEEN_QUESTIONS = 15    # secondes entre deux questions
    _USER_IDLE_SECONDS = 120         # pause auto-learner si activité chat < N secondes
    # Mode accéléré (première génération d'insights)
    _FAST_SLEEP_BETWEEN_NOTES = 0    # secondes entre deux notes en mode accéléré
    _FAST_SLEEP_BETWEEN_QUESTIONS = 0  # pas de pause entre questions en mode accéléré
    _FAST_SLEEP_AFTER_SEMANTIC = 0     # pas de pause après extraction sémantique
    _MAX_QUESTION_RETRIES = 3          # tentatives max si la réponse est insuffisante

    def __init__(self, chroma, rag, indexer, ui_active_fn=None, metrics: MetricsRecorder | None = None) -> None:
        self._chroma = chroma
        self._rag = rag
        self._indexer = indexer
        self._ui_active_fn = ui_active_fn or (lambda: True)  # par défaut : considère l'UI active
        self._question_prompt = _QUESTION_PROMPT
        self._web_answer_prompt = _WEB_ANSWER_PROMPT
        self._metrics = metrics or MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
        self._last_user_activity: float = 0.0  # timestamp epoch
        self._activity_lock = threading.Lock()
        self._processed_lock = threading.Lock()
        self._bulk_initial_done = threading.Event()  # signalé quand la passe initiale est finie
        # Statut lisible depuis l'UI (thread-safe via dict atomique Python)
        self.processing_status: dict = {
            "active": False,
            "note": "",
            "step": "",
            "log": [],  # liste de str (derniers messages)
            "bulk_pending_total": 0,  # notes à traiter dans le batch courant
            "bulk_new_done": 0,       # notes traitées dans le batch courant
        }
        self._scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1},
            timezone="UTC",
        )
        self._artifact_writer = AutoLearnArtifactWriter(self)
        self._entity_services = AutoLearnEntityServices(self)
        self._note_renamer = AutoLearnNoteRenamer(self)
        self._question_answering = AutoLearnQuestionAnswering(self)
        self._web_enrichment = AutoLearnWebEnrichment(self)
        self._synapse_discovery = AutoLearnSynapseDiscovery(self)

    @staticmethod
    def _get_settings():
        return settings

    @staticmethod
    def _utc_now() -> datetime:
        return _utc_now()

    @staticmethod
    def _normalize_entity_name(text: str) -> str:
        return _normalize_entity_name(text)

    @staticmethod
    def _wuddai_type_to_prefix() -> dict[str, str]:
        return _WUDDAI_TYPE_TO_PREFIX

    @staticmethod
    def _wuddai_image_types() -> list[str]:
        return _WUDDAI_IMAGE_TYPES

    # ---- Suivi des notes traitées ----

    def _load_processed(self) -> dict[str, str]:
        """Retourne {file_path: last_processed_iso}."""
        return self._json_store(settings.processed_notes_file).load({})

    def _save_processed(self, processed: dict[str, str]) -> None:
        """Écriture atomique via fichier temporaire + rename pour éviter les corruptions."""
        self._json_store(settings.processed_notes_file).save(processed, ensure_ascii=False, indent=2)

    def _mark_processed(self, file_path: str) -> None:
        with self._processed_lock:
            processed = self._load_processed()
            processed[file_path] = _utc_now_naive().isoformat()
            self._save_processed(processed)

    def _record_processing_time(self, secs: float) -> None:
        """Ajoute une durée (en secondes) à l'historique glissant (max 100 entrées)."""
        store = self._json_store(settings.processing_times_file)
        times: list[float] = store.load([])
        times.append(round(secs, 1))
        times = times[-100:]  # conserver les 100 dernières mesures
        try:
            store.save(times)
        except Exception:
            pass

    def _json_store(self, path: Path) -> JsonStateStore:
        return JsonStateStore(path, os_module=os, tempfile_module=tempfile)

    def _is_first_insight_run(self) -> bool:
        """Vrai si le bulk initial n'a jamais été complété.
        Une fois le bulk terminé, le fichier bulk_done.flag est créé et cette méthode retourne False."""
        if settings.bulk_done_flag_file.exists():
            return False
        processed_map = self._load_processed()
        try:
            all_notes = self._list_user_notes()
            unprocessed = sum(1 for n in all_notes if n["file_path"] not in processed_map)
            return unprocessed >= 10
        except Exception:
            return False

    def _list_user_notes(self) -> list[dict]:
        list_user_notes = getattr(self._chroma, "list_user_notes", None)
        if callable(list_user_notes):
            notes = list_user_notes()
            if isinstance(notes, list):
                return notes
        return [
            note for note in self._chroma.list_notes()
            if not self._is_obsirag_generated(note["file_path"])
        ]

    def _select_bulk_pending_notes(
        self,
        all_notes: list[dict],
        processed_map: dict[str, str],
    ) -> tuple[list[dict], int, int]:
        already_done = sum(1 for note in all_notes if note["file_path"] in processed_map)
        pending_notes = [note for note in all_notes if note["file_path"] not in processed_map]
        pending_total = len(pending_notes)
        bulk_max = settings.autolearn_bulk_max_notes
        if bulk_max > 0 and pending_total > bulk_max:
            logger.info(
                f"Auto-learner mode accéléré — limité à {bulk_max} notes sur {pending_total} en attente"
            )
            pending_notes = pending_notes[:bulk_max]
            pending_total = len(pending_notes)
        return pending_notes, pending_total, already_done

    def _warmup_search_backend(
        self,
        *,
        attempts: int = 10,
        delay_seconds: int = 3,
        ready_message: str,
        waiting_prefix: str,
    ) -> None:
        for attempt in range(attempts):
            try:
                self._chroma.search("warm-up", top_k=1)
                logger.info(ready_message)
                return
            except Exception as warm_exc:
                logger.info(f"{waiting_prefix} ({attempt + 1}/{attempts}) : {warm_exc}")
                time.sleep(delay_seconds)

    def _process_and_mark_note(
        self,
        note_meta: dict,
        *,
        sleep_between_questions: int | None = None,
        sleep_after_note: int = 0,
        error_prefix: str,
    ) -> bool:
        try:
            started_at = time.perf_counter()
            self._process_note(note_meta, sleep_between_questions=sleep_between_questions)
            self._mark_processed(note_meta["file_path"])
            if sleep_after_note > 0:
                time.sleep(sleep_after_note)
            self._record_processing_time(time.perf_counter() - started_at)
            return True
        except Exception as exc:
            logger.warning(f"{error_prefix} {note_meta['file_path']} : {exc}")
            return False

    def _finalize_bulk_initial(self) -> None:
        try:
            import mlx.core as mx
            mx.metal.clear_cache()
            logger.debug("Cache Metal MLX libéré (fin mode accéléré)")
        except Exception:
            pass
        if not self._ui_active_fn():
            logger.info("Auto-learner bulk : UI inactif — déchargement du modèle MLX")
            try:
                self._rag._llm.unload()
            except Exception as exc:
                logger.warning(f"Auto-learner bulk : erreur déchargement modèle : {exc}")
        self.processing_status["bulk_pending_total"] = 0
        self.processing_status["bulk_new_done"] = 0
        try:
            flag_file = settings.bulk_done_flag_file
            flag_file.parent.mkdir(parents=True, exist_ok=True)
            flag_file.touch()
        except Exception:
            pass
        self._bulk_initial_done.set()
        self._clear_status()

    def _recent_cycle_notes(
        self,
        processed_map: dict[str, str],
        cutoff_iso: str,
    ) -> list[dict]:
        since = _utc_now_naive() - timedelta(hours=settings.autolearn_lookback_hours)
        recent = self._chroma.get_recently_modified(since)
        return [
            note for note in recent
            if not self._is_obsirag_generated(note["file_path"])
            and not (processed_map.get(note["file_path"], "") > cutoff_iso)
        ]

    def _fullscan_cycle_notes(
        self,
        all_notes: list[dict],
        processed_map: dict[str, str],
        cutoff_iso: str,
        processed_in_pass1: set[str],
    ) -> list[dict]:
        def _sort_key(note: dict) -> str:
            return processed_map.get(note["file_path"], "")

        return [
            note for note in sorted(all_notes, key=_sort_key)
            if note["file_path"] not in processed_in_pass1
            and not self._is_obsirag_generated(note["file_path"])
            and not (
                processed_map.get(note["file_path"], "")
                and processed_map.get(note["file_path"], "") > cutoff_iso
            )
        ]

    def _run_bulk_initial(self) -> None:
        """Passe initiale accélérée : traite toutes les notes non traitées sans limite de quota
        et avec des pauses minimales. Appelée une seule fois au premier démarrage.
        Le cycle normal prend le relai une fois cette passe terminée."""
        # Chargement du modèle LLM avant la passe bulk.
        try:
            self._rag._llm.load()
        except Exception as exc:
            logger.error(f"Auto-learner bulk : impossible de charger le modèle LLM : {exc}")
            self._bulk_initial_done.set()
            return
        try:
            # Pré-calcul immédiat de pending_total (list_notes n'utilise pas les embeddings)
            # → bulk_pending_total visible dans le panel Insights dès le lancement du thread,
            #   sans attendre la fin du warm-up.
            all_notes = self._list_user_notes()
            processed_map = self._load_processed()
            pending_notes, pending_total, already_done = self._select_bulk_pending_notes(
                all_notes,
                processed_map,
            )
            new_done = 0
            self.processing_status["bulk_pending_total"] = pending_total
            self.processing_status["bulk_new_done"] = 0
            logger.info(f"Auto-learner mode accéléré — {pending_total} note(s) à traiter ({already_done} déjà traitées)")

            # Warm-up : attendre que le modèle d'embedding soit prêt pour la recherche
            self._warmup_search_backend(
                ready_message="Auto-learner mode accéléré — embedding prêt, démarrage du bulk",
                waiting_prefix="Auto-learner : attente embedding",
            )

            for note_meta in pending_notes:
                self._set_status(
                    note=note_meta.get("title", note_meta["file_path"]),
                    step=f"[Accéléré] {new_done + 1}/{pending_total} — en cours…",
                )
                if self._process_and_mark_note(
                    note_meta,
                    sleep_between_questions=self._FAST_SLEEP_BETWEEN_QUESTIONS,
                    sleep_after_note=self._FAST_SLEEP_BETWEEN_NOTES,
                    error_prefix="Auto-learner accéléré : erreur sur",
                ):
                    new_done += 1
                    self.processing_status["bulk_new_done"] = new_done
                    self._set_status(
                        note=note_meta.get("title", note_meta["file_path"]),
                        step=f"[Accéléré] {new_done}/{pending_total} ✓",
                    )

            logger.info(f"Auto-learner mode accéléré terminé — {new_done}/{pending_total} note(s) traitée(s)")
        except Exception as exc:
            logger.error(f"Auto-learner bulk initial error : {exc}")
        finally:
            self._finalize_bulk_initial()

    def start(self) -> None:
        interval = settings.autolearn_interval_minutes

        if self._is_first_insight_run():
            logger.info("Auto-learner : première utilisation détectée — mode accéléré dans 120s")
            # Délai de 120s avant de charger MLX : laisse Streamlit démarrer complètement
            # et évite le crash Metal GPU lors des redémarrages rapides par launchd.
            def _delayed_bulk():
                import time as _time
                _time.sleep(120)
                self._run_bulk_initial()
            bulk_thread = threading.Thread(
                target=_delayed_bulk,
                daemon=True,
                name="autolearn-bulk-initial",
            )
            bulk_thread.start()
            # Premier cycle normal différé : après la fin du bulk OU au bout de 24h max
            def _wait_and_schedule():
                self._bulk_initial_done.wait(timeout=86400)
                self._scheduler.add_job(
                    self._run_cycle,
                    "interval",
                    minutes=interval,
                    id="autolearn_cycle",
                    next_run_time=_utc_now() + timedelta(minutes=5),
                )
                logger.info("Auto-learner mode accéléré terminé — cycle normal activé")
            threading.Thread(target=_wait_and_schedule, daemon=True, name="autolearn-scheduler-init").start()
        else:
            self._bulk_initial_done.set()  # pas de passe initiale nécessaire
            self._scheduler.add_job(
                self._run_cycle,
                "interval",
                minutes=interval,
                id="autolearn_cycle",
                next_run_time=_utc_now() + timedelta(minutes=5),
            )

        # Synthèse hebdomadaire le dimanche à 20h UTC.
        # misfire_grace_time = 7 jours : si le Mac était en veille au moment
        # du déclenchement prévu, APScheduler exécutera la synthèse dès le réveil
        # plutôt que de l'ignorer.
        self._scheduler.add_job(
            self._weekly_synthesis,
            "cron",
            day_of_week="sun",
            hour=20,
            minute=0,
            id="weekly_synthesis",
            misfire_grace_time=7 * 24 * 3600,  # 7 jours en secondes
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
        entry = {"ts": _utc_now_naive().isoformat(), "query": query}
        self._json_store(settings.queries_file).append_json_line(entry)

    # ---- Cycle principal ----

    def _set_status(self, note: str = "", step: str = "", active: bool = True) -> None:
        """Met à jour le statut de traitement (thread-safe)."""
        log = self.processing_status["log"]
        if step:
            log.append(f"{datetime.now().strftime('%H:%M:%S')} — {step}")
            if len(log) > 20:  # garder les 20 derniers messages
                log.pop(0)
        self.processing_status.update({"active": active, "note": note, "step": step})
        self._persist_status()

    def _clear_status(self) -> None:
        self.processing_status.update({"active": False, "note": "", "step": ""})
        self._persist_status()

    def _persist_status(self) -> None:
        """Écrit processing_status dans un fichier JSON pour survivre aux redémarrages."""
        try:
            self._json_store(settings.processing_status_file).save(self.processing_status, ensure_ascii=False)
        except Exception:
            pass

    @staticmethod
    def _is_obsirag_generated(file_path: str) -> bool:
        """Retourne True si la note est générée par ObsiRAG (insights, synthesis, synapses).
        Ces notes ne doivent pas être retraitées par l'auto-learner pour éviter les boucles."""
        p = file_path.replace("\\", "/")
        return "/obsirag/" in p or p.startswith("obsirag/")

    def _run_cycle(self) -> None:
        cycle_started_at = time.perf_counter()
        # Vérification de la plage horaire autorisée
        current_hour = datetime.now().hour
        h_start = settings.autolearn_active_hour_start
        h_end = settings.autolearn_active_hour_end
        if not (h_start <= current_hour < h_end):
            logger.info(
                f"Auto-learner : cycle ignoré (heure {current_hour:02d}h hors plage {h_start:02d}h-{h_end:02d}h)"
            )
            return

        logger.info("Auto-learner : début du cycle")
        # Chargement du modèle LLM avant le cycle.
        try:
            self._rag._llm.load()
        except Exception as exc:
            logger.error(f"Auto-learner : impossible de charger le modèle LLM : {exc}")
            return
        try:
            # Vérifier que la couche de recherche / embeddings est prête avant de démarrer le cycle
            try:
                self._chroma.search("warm-up", top_k=1)
            except Exception as warm_exc:
                logger.warning(f"Auto-learner : backend de recherche non prêt, cycle annulé : {warm_exc}")
                return

            processed_count = 0
            processed_map = self._load_processed()

            # Seuil commun aux deux passes : ne pas retraiter avant N jours
            min_reprocess_delta = timedelta(days=settings.autolearn_min_reprocess_days)
            cutoff_iso = (_utc_now_naive() - min_reprocess_delta).isoformat()

            # Pass 1 — notes récemment modifiées (hors notes générées par ObsiRAG)
            recent_filtered = self._recent_cycle_notes(processed_map, cutoff_iso)
            for note_meta in recent_filtered[: settings.autolearn_max_notes_per_run]:
                self._wait_for_idle(note_meta.get("title", ""))
                if self._process_and_mark_note(
                    note_meta,
                    sleep_after_note=self._SLEEP_BETWEEN_NOTES,
                    error_prefix="Auto-learner : erreur sur",
                ):
                    processed_count += 1

            # Pass 2 — full-scan progressif : notes jamais traitées ou les plus anciennes
            all_notes = self._list_user_notes()
            processed_in_pass1 = {n["file_path"] for n in recent_filtered[: settings.autolearn_max_notes_per_run]}
            pending = self._fullscan_cycle_notes(
                all_notes,
                processed_map,
                cutoff_iso,
                processed_in_pass1,
            )
            quota = settings.autolearn_fullscan_per_run
            for note_meta in pending:
                if quota <= 0:
                    break
                self._wait_for_idle(note_meta.get("title", ""))
                if self._process_and_mark_note(
                    note_meta,
                    sleep_after_note=self._SLEEP_BETWEEN_NOTES,
                    error_prefix="Auto-learner full-scan : erreur sur",
                ):
                    processed_count += 1
                    quota -= 1

            logger.info(f"Auto-learner : {processed_count} note(s) traitée(s)")

            # Pass 3 — découverte de synapses (connexions implicites)
            self._set_status(note="Synapses", step="Découverte de connexions implicites…")
            self._discover_synapses(all_notes)

        except Exception as exc:
            logger.error(f"Auto-learner cycle error : {exc}")
        finally:
            try:
                self._metrics.observe("autolearn_cycle_seconds", time.perf_counter() - cycle_started_at)
            except Exception:
                pass
            try:
                import mlx.core as mx
                mx.metal.clear_cache()
                logger.debug("Cache Metal MLX libéré (fin cycle)")
            except Exception:
                pass
            self._clear_status()

    def _process_note(
        self,
        note_meta: dict,
        sleep_between_questions: int | None = None,
    ) -> None:
        _sleep_q = sleep_between_questions if sleep_between_questions is not None else self._SLEEP_BETWEEN_QUESTIONS
        title = note_meta.get("title", note_meta["file_path"])
        logger.info(f"Auto-learner : traitement de '{title}'")
        self._set_status(note=title, step="Récupération des chunks…")

        chunks = self._chroma.search(title, top_k=5)
        if not chunks:
            logger.warning(f"Auto-learner : aucun chunk trouvé pour '{title}'")
            self._set_status(note=title, step="⚠️ Aucun chunk trouvé, note ignorée")
            try:
                self._metrics.increment("autolearn_notes_skipped_total")
            except Exception:
                pass
            return

        content_preview = "\n\n".join(c["text"] for c in chunks[:3])
        qa_pair = self._question_answering.generate_valid_qa_pair(
            title,
            content_preview,
            sleep_between_questions=_sleep_q,
            max_retries=self._MAX_QUESTION_RETRIES,
        )
        qa_pairs = [qa_pair] if qa_pair else []

        if qa_pairs:
            self._set_status(note=title, step=f"Sauvegarde de l'insight ({len(qa_pairs)} Q&A)…")
            self._save_knowledge_artifact(title, note_meta, qa_pairs)
            self._set_status(note=title, step=f"✅ Insight sauvegardé ({len(qa_pairs)} Q&A)")
        else:
            self._set_status(note=title, step="⚠️ Aucune réponse QA valide, insight non créé")
            logger.warning(f"Auto-learner : aucune réponse QA pour '{title}', artefact non créé")
            try:
                self._metrics.increment("autolearn_notes_skipped_total")
            except Exception:
                pass

        # ---- Auto-renommage : titre représentatif via IA ----
        # Restriction : uniquement les notes dans obsirag/ (insights, rapports internes…)
        # Les notes personnelles (hors obsirag/) ne sont JAMAIS renommées.
        fp = note_meta.get("file_path", "")
        if fp and self._is_obsirag_generated(fp):
            abs_path = settings.vault / fp
            if abs_path.exists():
                self._set_status(note=title, step="Suggestion d'un titre représentatif…")
                new_title = self._suggest_note_title(content_preview, title)
                if new_title:
                    self._set_status(note=title, step=f"Renommage : '{new_title}'…")
                    result = self._rename_note_in_vault(abs_path, new_title, fp)
                    if result:
                        # Mettre à jour note_meta avec le nouveau chemin relatif
                        # pour que _mark_processed (appelé par le caller) utilise
                        # le chemin cohérent avec ChromaDB
                        try:
                            new_rel = str(result.relative_to(settings.vault))
                            note_meta["file_path"] = new_rel
                        except Exception:
                            pass
                        self._set_status(note=new_title, step=f"✅ Note renommée → '{new_title}'")
                    else:
                        self._set_status(note=title, step="⚠️ Renommage annulé (conflit ou erreur)")

    def _is_weak_answer(self, answer: str) -> bool:
        return len(answer.strip()) < _MIN_ANSWER_LENGTH or bool(_WEAK_ANSWER_PATTERNS.search(answer))

    # Budget de contexte — évite les erreurs "Context size exceeded"
    _PROMPT_OVERHEAD_CHARS = 400   # overhead fixe du template (question + labels + ponctuation)
    _MAX_TOKENS_RESPONSE   = 1500  # tokens réservés pour la réponse du modèle

    def _fit_context(
        self,
        rag_ctx: str,
        web_ctx: str,
        overhead: int = _PROMPT_OVERHEAD_CHARS,
    ) -> tuple[str, str]:
        """
        Tronque rag_ctx et web_ctx pour que le prompt complet respecte la fenêtre
        de contexte configuré (settings.ollama_context_size).

        Budget = (n_ctx - max_tokens_réponse) × 4 chars/token − overhead
        Allocation : 30 % pour rag_ctx, 70 % pour web_ctx.
        """
        chars_per_token = 4
        total_budget = (
            settings.ollama_context_size - self._MAX_TOKENS_RESPONSE
        ) * chars_per_token - overhead
        total_budget = max(total_budget, 800)  # plancher de sécurité

        rag_budget = int(total_budget * 0.30)
        web_budget = total_budget - rag_budget

        fitted_rag = rag_ctx[:rag_budget]
        fitted_web = web_ctx[:web_budget]
        if len(rag_ctx) > rag_budget or len(web_ctx) > web_budget:
            logger.debug(
                f"fit_context : rag {len(rag_ctx)}→{len(fitted_rag)} chars, "
                f"web {len(web_ctx)}→{len(fitted_web)} chars "
                f"(budget={total_budget}, n_ctx={settings.ollama_context_size})"
            )
        return fitted_rag, fitted_web

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
        return AutoLearnWebEnrichment.fetch_url_content(url, max_chars=max_chars)

    def _synthesize_web_sources(self, note_title: str, qa_pairs: list[dict]) -> str:
        return self._web_enrichment.synthesize_web_sources(note_title, qa_pairs)

    def _web_search(self, query: str) -> list[dict]:
        return self._web_enrichment.web_search(query)

    @staticmethod
    def _snippets_relevant(question: str, snippets: list[str]) -> bool:
        return AutoLearnWebEnrichment.snippets_relevant(question, snippets)

    def _enrich_with_web(self, question: str, rag_answer: str, web_snippets: list[str]) -> str:
        return self._web_enrichment.enrich_with_web(question, rag_answer, web_snippets)

    def _generate_questions(self, content: str, already_asked: list[str] | None = None) -> list[str]:
        return self._web_enrichment.generate_questions(content, already_asked=already_asked)

    def _load_wuddai_entities(self) -> list[dict]:
        return self._entity_services.load_wuddai_entities()

    def _extract_validated_entities(self, text: str) -> tuple[list[str], list[dict]]:
        return self._entity_services.extract_validated_entities(text)

    @staticmethod
    def _entities_to_tags_spacy(text: str) -> list[str]:
        return AutoLearnEntityServices.entities_to_tags_spacy(text)

    @staticmethod
    def _build_entity_image_gallery(entity_images: list[dict]) -> str:
        return AutoLearnEntityServices.build_entity_image_gallery(entity_images)

    # ---- Helpers frontmatter ----

    @staticmethod
    def _fm_end(content: str) -> int:
        """Position du 1er caractère après la ligne de fermeture --- du frontmatter.
        Utilise ^---$ (début de ligne) pour éviter les faux positifs. Retourne -1 si absent."""
        if not content.startswith("---"):
            return -1
        matches = list(re.finditer(r"^---[ \t]*$", content, re.MULTILINE))
        if len(matches) < 2:
            return -1
        end = matches[1].end()
        if end < len(content) and content[end] == "\n":
            end += 1
        return end

    @staticmethod
    def _read_frontmatter_tags(content: str) -> list[str]:
        """Extrait les tags du frontmatter YAML d'un fichier Markdown."""
        end = AutoLearner._fm_end(content)
        if end == -1:
            return []
        yaml_block = content[3:end]
        tags: list[str] = []
        in_tags = False
        for line in yaml_block.splitlines():
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

    def _fetch_gpe_coordinates(self, entity_name: str) -> tuple[float, float] | None:
        return self._entity_services.fetch_gpe_coordinates(entity_name)

    @staticmethod
    def _add_location_to_frontmatter(content: str, lat: float, lng: float) -> str:
        """Ajoute ou remplace le champ `location` dans le frontmatter YAML (format Obsidian Map View)."""
        location_line = f"location: [{lat:.6f}, {lng:.6f}]"
        end = AutoLearner._fm_end(content)
        if end == -1:
            return f"---\n{location_line}\n---\n" + content
        yaml_block = content[3:end]
        yaml_lines = [l for l in yaml_block.splitlines() if not l.startswith("location:")]
        yaml_lines.append(location_line)
        body = content[end:]
        return "---\n" + "\n".join(yaml_lines) + "\n---\n" + body

    @staticmethod
    def _merge_frontmatter_tags(content: str, new_tags: list[str]) -> str:
        """Ajoute de nouveaux tags au frontmatter YAML sans doublons."""
        existing = AutoLearner._read_frontmatter_tags(content)
        merged = list(existing)
        for t in new_tags:
            if t not in merged:
                merged.append(t)
        fm = "---\ntags:\n" + "\n".join(f"  - {t}" for t in merged) + "\n---\n"
        end = AutoLearner._fm_end(content)
        if end == -1:
            return fm + content
        return fm + content[end:]

    # ---- Recherche et mise à jour d'artefacts existants ----

    def _find_existing_insight(self, note_title: str, ner_tags: list[str]) -> Path | None:
        return self._artifact_writer.find_existing_insight(note_title, ner_tags)

    @staticmethod
    def _wikilink(file_path: str) -> str:
        return AutoLearnArtifactWriter.wikilink(file_path)

    @staticmethod
    def _compute_global_provenance(qa_pairs: list[dict]) -> str:
        return AutoLearnArtifactWriter.compute_global_provenance(qa_pairs)

    def _render_qa_sections(self, qa_pairs: list[dict], *, start_index: int = 1, provenance: str) -> list[str]:
        return self._artifact_writer.render_qa_sections(qa_pairs, start_index=start_index, provenance=provenance)

    def _render_web_synthesis_section(self, note_title: str, qa_pairs: list[dict]) -> list[str]:
        return self._artifact_writer.render_web_synthesis_section(note_title, qa_pairs)

    def _maybe_add_frontmatter_location(self, content: str, entity_images: list[dict] | None) -> str:
        return self._artifact_writer.maybe_add_frontmatter_location(content, entity_images)

    def _upsert_entity_gallery(self, content: str, entity_images: list[dict] | None) -> str:
        return self._artifact_writer.upsert_entity_gallery(content, entity_images)

    def _build_new_insight_document(
        self,
        note_title: str,
        note_meta: dict,
        qa_pairs: list[dict],
        source_tags: list[str],
        ner_tags: list[str],
        entity_images: list[dict],
        global_provenance: str,
    ) -> str:
        return self._artifact_writer.build_new_insight_document(
            note_title,
            note_meta,
            qa_pairs,
            source_tags,
            ner_tags,
            entity_images,
            global_provenance,
        )

    def _append_to_insight(
        self,
        path: Path,
        qa_pairs: list[dict],
        ner_tags: list[str],
        provenance: str,
        entity_images: list[dict] | None = None,
    ) -> None:
        self._artifact_writer.append_to_insight(path, qa_pairs, ner_tags, provenance, entity_images)

    # ---- Sauvegarde / création d'artefact ----

    def _save_knowledge_artifact(
        self,
        note_title: str,
        note_meta: dict,
        qa_pairs: list[dict],
    ) -> None:
        self._artifact_writer.save_knowledge_artifact(note_title, note_meta, qa_pairs)

    # ---- Découverte de synapses ----

    def _load_synapse_index(self) -> set[str]:
        return self._synapse_discovery.load_synapse_index()

    def _save_synapse_index(self, index: set[str]) -> None:
        self._synapse_discovery.save_synapse_index(index)

    @staticmethod
    def _synapse_pair_key(fp_a: str, fp_b: str) -> str:
        return AutoLearnSynapseDiscovery.synapse_pair_key(fp_a, fp_b)

    def _discover_synapses(self, all_notes: list[dict]) -> None:
        self._synapse_discovery.discover_synapses(all_notes)

    def _create_synapse_artifact(self, note_a: dict, note_b_info: dict) -> None:
        self._synapse_discovery.create_synapse_artifact(note_a, note_b_info)

    # ---- Synthèse hebdomadaire ----

    def _suggest_note_title(self, content_preview: str, current_title: str) -> str | None:
        return self._note_renamer.suggest_note_title(content_preview, current_title)

    def _rename_note_in_vault(
        self,
        old_abs: "Path",
        new_title: str,
        note_rel: str,
    ) -> "Path | None":
        return self._note_renamer.rename_note_in_vault(old_abs, new_title, note_rel)

    # ---- Synthèse hebdomadaire ----

    def _weekly_synthesis(self) -> None:
        logger.info("Auto-learner : génération de la synthèse hebdomadaire")
        try:
            since = _utc_now_naive() - timedelta(days=7)
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

            week = _utc_now().strftime("%Y-W%W")
            out_dir = settings.synthesis_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"semaine_{week}.md"
            header = (
                f"# Synthèse de la semaine {week}\n\n"
                f"*Générée automatiquement par ObsiRAG le "
                f"{_utc_now().strftime('%Y-%m-%d %H:%M')} UTC*\n\n---\n\n"
            )
            out_path.write_text(header + synthesis, encoding="utf-8")
            logger.info(f"Synthèse hebdomadaire : {out_path.name}")

        except Exception as exc:
            logger.error(f"Synthèse hebdomadaire échouée : {exc}")
