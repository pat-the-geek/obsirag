from __future__ import annotations

import re
import unicodedata
from typing import Any

from loguru import logger

from src.learning.entity_cache import GeocodeCache, WuddaiCache


class AutoLearnEntityServices:
    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def load_wuddai_entities(self) -> list[dict]:
        settings = self._owner._get_settings()
        cache = WuddaiCache(
            data_dir=settings.data_dir,
            utc_now_fn=self._owner._utc_now,
            normalize_fn=self._owner._normalize_entity_name,
            wuddai_url=settings.wuddai_entities_url,
        )
        return cache.load()

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
        cache = GeocodeCache(
            data_dir=settings.data_dir,
            normalize_fn=self._owner._normalize_entity_name,
        )
        return cache.get_coords(entity_name)

    @staticmethod
    def _extract_spacy_candidates(text: str) -> list[tuple[str, str]]:
        try:
            from src.vault.parser import get_nlp

            nlp = get_nlp()
            doc = nlp(text[:10_000])
            return [(ent.text.strip(), ent.label_) for ent in doc.ents if len(ent.text.strip()) >= 3]
        except Exception:
            return []