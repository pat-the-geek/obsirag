from __future__ import annotations

import time
import unicodedata
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.storage.slugify import build_ascii_stem

if TYPE_CHECKING:
    from src.learning.autolearn import AutoLearner

_WUDDAI_TYPE_LABELS: dict[str, str] = {
    "PERSON":  "Personne",
    "ORG":     "Organisation",
    "GPE":     "Lieu",
    "LOC":     "Lieu",
    "FAC":     "Lieu",
    "PRODUCT": "Produit",
    "EVENT":   "Événement",
    "NORP":    "Groupe",
}

_WUDDAI_TAG_PREFIXES: dict[str, str] = {
    "PERSON":  "personne",
    "ORG":     "org",
    "GPE":     "lieu",
    "LOC":     "lieu",
    "FAC":     "lieu",
    "PRODUCT": "produit",
    "EVENT":   "event",
    "NORP":    "groupe",
}

# Fallback pour les entités non trouvées dans WUDD.ai (lance NER type → label)
_NER_TYPE_LABELS: dict[str, str] = {
    "persons":   "Personne",
    "orgs":      "Organisation",
    "locations": "Lieu",
}
_NER_TAG_PREFIXES: dict[str, str] = {
    "persons":   "personne",
    "orgs":      "org",
    "locations": "lieu",
}

_SLEEP_BETWEEN_ENTITIES = 3.0
_MAX_NOTES_PER_ENTITY = 50
_MAX_NEW_PER_CYCLE = 50


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class EntityNotesGenerator:
    def __init__(self, owner: "AutoLearner") -> None:
        self._owner = owner

    def generate(self) -> int:
        settings = self._owner._get_settings()
        entities_dir = settings.entities_dir
        entities_dir.mkdir(parents=True, exist_ok=True)

        raw_map = self._owner._chroma.get_entity_to_notes_map(min_notes=2, min_chars=4)
        validated = self._validate_with_wuddai(raw_map)

        written = 0
        new_this_cycle = 0
        active_slugs: set[str] = set()

        # Prioritize new entities (no existing note) to fill quota first
        def _sort_key(item: tuple[str, dict]) -> int:
            name, _ = item
            slug = build_ascii_stem(name, max_length=60)
            return 0 if slug and not (entities_dir / f"{slug}.md").exists() else 1

        sorted_entities = sorted(validated.items(), key=_sort_key)

        for official_name, info in sorted_entities:
            slug = build_ascii_stem(official_name, max_length=60)
            if not slug:
                continue
            active_slugs.add(slug)
            note_path = entities_dir / f"{slug}.md"
            is_new = not note_path.exists()

            # Quota: stop creating new notes once limit reached; still update existing
            if is_new and new_this_cycle >= _MAX_NEW_PER_CYCLE:
                continue

            try:
                summary = self._generate_summary(official_name, note_path)
                content = self._render_note(official_name, info, summary)
                note_path.write_text(content, encoding="utf-8")
                written += 1
                if is_new:
                    new_this_cycle += 1
                action = "créée" if is_new else "mise à jour"
                wuddai_type = info.get("wuddai_type", "?")
                logger.info(
                    f"EntityNotes: [{wuddai_type}] '{official_name}' — {action}"
                    f" ({info.get('count', 0)} notes)"
                )
                if is_new and summary:
                    time.sleep(_SLEEP_BETWEEN_ENTITIES)
            except Exception as exc:
                logger.warning(f"EntityNotes: échec pour '{official_name}': {exc}")

        self._cleanup_stale(entities_dir, active_slugs)
        total_existing = len(list(entities_dir.glob("*.md")))
        logger.info(
            f"EntityNotes: {written} note(s) écrites ({new_this_cycle} nouvelles) — "
            f"{total_existing} au total dans {entities_dir}"
        )
        return written

    def _validate_with_wuddai(self, raw_map: dict[str, dict]) -> dict[str, dict]:
        """Filtre les entités via WUDD.ai — retourne uniquement les entités reconnues.

        Utilise le nom officiel et le type WUDD.ai. En cas d'indisponibilité,
        applique un filtre basique (majuscule initiale, longueur minimale).
        """
        wuddai = self._owner._load_wuddai_entities()

        if not wuddai:
            logger.debug("EntityNotes: WUDD.ai indisponible — filtre basique appliqué")
            return self._basic_filter(raw_map)

        wuddai_index: dict[str, dict] = {
            entity["value_normalized"]: entity for entity in wuddai
        }

        result: dict[str, dict] = {}
        for raw_name, info in raw_map.items():
            normalized = _normalize(raw_name)
            if not normalized:
                continue

            match = wuddai_index.get(normalized)
            if not match:
                # Recherche partielle souple (même logique que entity_services.py)
                for key, entity in wuddai_index.items():
                    if (normalized in key or key in normalized) and abs(len(normalized) - len(key)) <= 5:
                        match = entity
                        break

            if not match:
                continue

            official_name: str = match["value"]
            wuddai_type: str = match["type"]

            # Merge notes si l'entité officielle est déjà dans le résultat
            if official_name in result:
                existing_notes = {n["file_path"] for n in result[official_name]["notes"]}
                for note in info["notes"]:
                    if note["file_path"] not in existing_notes:
                        result[official_name]["notes"].append(note)
                result[official_name]["count"] = len(result[official_name]["notes"])
            else:
                result[official_name] = {
                    "wuddai_type": wuddai_type,
                    "count": info["count"],
                    "notes": list(info["notes"]),
                }

        logger.info(f"EntityNotes: {len(raw_map)} entités brutes → {len(result)} validées WUDD.ai")
        return result

    def _basic_filter(self, raw_map: dict[str, dict]) -> dict[str, dict]:
        """Filtre minimal quand WUDD.ai est indisponible."""
        stop = frozenset({
            "Conclusion", "Introduction", "Contexte", "Source", "Sources",
            "Note", "Notes", "Impact", "Résumé", "Suite", "Partie",
            "Intelligence", "Information", "Données", "Résultats",
            "The", "This", "AI", "IA",
        })
        result = {}
        for name, info in raw_map.items():
            if name in stop or len(name) < 3 or not name[0].isupper():
                continue
            result[name] = {**info, "wuddai_type": None}
        return result

    def _generate_summary(self, entity_name: str, note_path: Path) -> str:
        """Résumé RAG de ce que le coffre dit sur l'entité.

        Réutilise le résumé existant si la note est déjà présente — évite un
        appel LLM à chaque cycle.
        """
        if note_path.exists():
            existing = note_path.read_text(encoding="utf-8", errors="replace")
            marker = "## Ce que le coffre dit"
            if marker in existing:
                start = existing.index(marker) + len(marker)
                end = existing.find("\n## ", start)
                snippet = existing[start:end if end != -1 else start + 600].strip()
                if len(snippet) > 50:
                    return snippet

        try:
            answer, _ = self._owner._rag.query(
                f"Que dit le coffre sur {entity_name} ? Résume en 3 à 5 phrases.",
                chat_history=[],
                exclude_obsirag_generated=True,
            )
            text = str(answer or "").strip()
            if text.lower() == "cette information n'est pas dans ton coffre." or len(text) < 20:
                return ""
            return text
        except Exception as exc:
            logger.debug(f"EntityNotes: résumé RAG indisponible pour '{entity_name}': {exc}")
            return ""

    def _render_note(self, entity_name: str, info: dict, summary: str) -> str:
        wuddai_type = info.get("wuddai_type")
        ner_type = info.get("type", "persons")

        type_label = _WUDDAI_TYPE_LABELS.get(wuddai_type or "", "") or _NER_TYPE_LABELS.get(ner_type, "Entité")
        tag_prefix = _WUDDAI_TAG_PREFIXES.get(wuddai_type or "", "") or _NER_TAG_PREFIXES.get(ner_type, "entity")

        notes = info.get("notes", [])[:_MAX_NOTES_PER_ENTITY]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        slug_tag = build_ascii_stem(entity_name, max_length=40)

        lines = [
            "---",
            "tags:",
            "  - entity",
            "  - obsirag",
            f"  - {tag_prefix}/{slug_tag}",
            f"entity_type: {wuddai_type or ner_type}",
            f"entity_name: {entity_name}",
            "---",
            "",
            f"# {entity_name}",
            "",
            f"**Type :** {type_label}  ",
            f"**Notes mentionnant cette entité :** {info.get('count', len(notes))}  ",
            f"**Mis à jour le :** {now}",
            "",
        ]

        if summary:
            lines += [
                "## Ce que le coffre dit",
                "",
                summary,
                "",
            ]

        lines += ["## Notes liées", ""]
        for note in notes:
            fp = note["file_path"]
            stem = fp[:-3] if fp.endswith(".md") else fp
            title = note.get("title") or Path(fp).stem
            lines.append(f"- [[{stem}|{title}]]")

        return "\n".join(lines) + "\n"

    def _cleanup_stale(self, entities_dir: Path, active_slugs: set[str]) -> None:
        if not entities_dir.exists():
            return
        for f in entities_dir.glob("*.md"):
            if f.stem not in active_slugs:
                try:
                    f.unlink()
                    logger.debug(f"EntityNotes: suppression note obsolète {f.name}")
                except Exception:
                    pass
