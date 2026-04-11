from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger


class AutoLearnEntityServices:
    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def load_wuddai_entities(self) -> list[dict]:
        cache_file = self._owner._get_settings().data_dir / "wuddai_entities_cache.json"
        if cache_file.exists():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                fetched_at = datetime.fromisoformat(cached.get("fetched_at", "2000-01-01"))
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=UTC)
                if self._owner._utc_now() - fetched_at < timedelta(hours=24):
                    return cached["entities"]
            except Exception:
                pass
        try:
            import urllib.request

            settings = self._owner._get_settings()
            url = f"{settings.wuddai_entities_url}/api/entities/export?limit=5000&images=true"
            req = urllib.request.Request(url, headers={"User-Agent": "ObsiRAG/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            entities = [
                {
                    "type": entity["type"],
                    "value": entity["value"],
                    "value_normalized": self._owner._normalize_entity_name(entity["value"]),
                    "mentions": entity.get("mentions", 0),
                    "image_url": entity.get("image", {}).get("url") if entity.get("image") else None,
                }
                for entity in data.get("entities", [])
            ]
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    {"fetched_at": self._owner._utc_now().isoformat(), "entities": entities},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info(f"WUDD.ai entities cache rafraîchi : {len(entities)} entités")
            return entities
        except Exception as exc:
            logger.warning(f"Impossible de charger les entités WUDD.ai : {exc}")
            return []

    def extract_validated_entities(self, text: str) -> tuple[list[str], list[dict]]:
        wuddai_entities = self._owner._load_wuddai_entities()
        if not wuddai_entities:
            return self._owner._entities_to_tags_spacy(text), []

        wuddai_index: dict[str, dict] = {entity["value_normalized"]: entity for entity in wuddai_entities}
        candidates = self._extract_spacy_candidates(text)

        tags: list[str] = []
        entity_images: list[dict] = []
        seen_tags: set[str] = set()
        seen_values: set[str] = set()

        for raw_value, _spacy_label in candidates:
            normalized = self._owner._normalize_entity_name(raw_value)
            if not normalized:
                continue
            match = wuddai_index.get(normalized)
            if not match:
                for key, entity in wuddai_index.items():
                    if (normalized in key or key in normalized) and abs(len(normalized) - len(key)) <= 5:
                        match = entity
                        break
            if not match:
                continue

            official_value = match["value"]
            official_type = match["type"]
            prefix = self._owner._wuddai_type_to_prefix().get(official_type)
            if not prefix:
                continue

            slug = re.sub(r"[^\w\s-]", "", self._owner._normalize_entity_name(official_value))
            slug = re.sub(r"[\s_]+", "-", slug)
            tag = f"{prefix}/{slug}"
            if tag not in seen_tags:
                seen_tags.add(tag)
                tags.append(tag)

            if official_type in self._owner._wuddai_image_types() and match.get("image_url") and official_value not in seen_values:
                seen_values.add(official_value)
                entity_images.append({
                    "type": official_type,
                    "value": official_value,
                    "image_url": match["image_url"],
                    "mentions": match.get("mentions", 0),
                })

        entity_images.sort(
            key=lambda entity: (
                self._owner._wuddai_image_types().index(entity["type"])
                if entity["type"] in self._owner._wuddai_image_types() else 99,
                -entity["mentions"],
            )
        )
        return tags[:20], entity_images

    @staticmethod
    def entities_to_tags_spacy(text: str) -> list[str]:
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
                    continue
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

    @staticmethod
    def build_entity_image_gallery(entity_images: list[dict]) -> str:
        if not entity_images:
            return ""
        by_type: dict[str, dict] = {}
        for entity in entity_images:
            if entity["type"] not in by_type:
                by_type[entity["type"]] = entity
        selected = [by_type[item_type] for item_type in ["PERSON", "ORG", "GPE", "PRODUCT"] if item_type in by_type]
        if not selected:
            return ""
        header = " | ".join(f"![{entity['value']}]({entity['image_url']})" for entity in selected)
        labels = " | ".join(f"**{entity['value']}**" for entity in selected)
        sep = " | ".join(":---:" for _ in selected)
        return f"| {header} |\n| {sep} |\n| {labels} |\n"

    def fetch_gpe_coordinates(self, entity_name: str) -> tuple[float, float] | None:
        settings = self._owner._get_settings()
        cache_file = settings.data_dir / "geocode_cache.json"
        try:
            cache: dict = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
        except Exception:
            cache = {}

        key = self._owner._normalize_entity_name(entity_name)
        if key in cache:
            return tuple(cache[key]) if cache[key] else None  # type: ignore[return-value]

        coords = None
        for lang in ("fr", "en"):
            try:
                import urllib.parse
                import urllib.request

                params = urllib.parse.urlencode({
                    "action": "query",
                    "prop": "coordinates",
                    "titles": entity_name,
                    "format": "json",
                    "redirects": "1",
                })
                url = f"https://{lang}.wikipedia.org/w/api.php?{params}"
                req = urllib.request.Request(url, headers={"User-Agent": "ObsiRAG/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                for page in pages.values():
                    coordinates = page.get("coordinates", [])
                    if coordinates:
                        coords = (coordinates[0]["lat"], coordinates[0]["lon"])
                        break
                if coords:
                    break
            except Exception:
                pass

        cache[key] = list(coords) if coords else None
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return coords

    @staticmethod
    def _extract_spacy_candidates(text: str) -> list[tuple[str, str]]:
        try:
            from src.vault.parser import get_nlp

            nlp = get_nlp()
            doc = nlp(text[:10_000])
            return [(ent.text.strip(), ent.label_) for ent in doc.ents if len(ent.text.strip()) >= 3]
        except Exception:
            return []