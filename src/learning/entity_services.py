from __future__ import annotations

import concurrent.futures
import json
import re
import ssl
import urllib.parse
import urllib.request
import unicodedata

_SSL_UNVERIFIED_CTX = ssl.create_default_context()
_SSL_UNVERIFIED_CTX.check_hostname = False
_SSL_UNVERIFIED_CTX.verify_mode = ssl.CERT_NONE
from pathlib import Path
from typing import Any

from loguru import logger

from src.learning.entity_cache import GeocodeCache, WuddaiCache


_DDG_TIMEOUT_SECONDS = 3
_DDG_ENTITY_MAX_WORKERS = 5
_DDG_USER_AGENT = "Mozilla/5.0 (ObsiRAG/1.0; +https://github.com/pat-the-geek/obsirag)"
_ENTITY_MATCH_STOPWORDS = {
    "qui", "que", "quoi", "est", "suis", "sont", "dans", "avec", "sans", "pour",
    "sur", "une", "des", "les", "par", "this", "that", "what", "when", "where",
    "who", "why", "how", "from", "into", "your", "vous", "nous", "leur", "elle",
    "lui", "son", "ses", "cet", "cette", "these", "those",
}
_FALLBACK_ENTITY_LABELS = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "GPE",
    "LOC": "LOC",
    "PRODUCT": "PRODUCT",
}
_PRODUCT_HINT_TOKENS = {
    "airpods", "airtag", "apple", "galaxy", "iphone", "ipad", "ipod", "macbook",
    "mac", "nintendo", "pixel", "playstation", "surface", "switch", "vision",
    "watch", "xbox",
}


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

    def lookup_wuddai_entity_contexts(
        self,
        text: str,
        *,
        max_entities: int = 10,
        max_notes: int = 3,
    ) -> list[dict]:
        if not text or not text.strip():
            return []

        entities = self._owner._load_wuddai_entities()
        notes = self._list_notes()
        matches = self._match_wuddai_entities(text, entities, max_entities=max_entities) if entities else []

        seen_values: set[str] = set()
        all_matches: list[dict] = []
        for match in matches:
            normalized = self._owner._normalize_entity_name(str(match.get("value") or ""))
            if normalized:
                seen_values.add(normalized)
            all_matches.append(match)

        remaining = max(0, max_entities - len(all_matches))
        if remaining:
            fallback_matches = self._extract_fallback_entities(text, excluded_values=seen_values, max_entities=remaining)
            all_matches.extend(fallback_matches)

        if not all_matches:
            return []

        # Fetch DDG knowledge for all entities in parallel
        max_workers = min(len(all_matches), _DDG_ENTITY_MAX_WORKERS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            ddg_futures = {
                match["value"]: executor.submit(self._fetch_ddg_entity_knowledge, match["value"])
                for match in all_matches
            }

        contexts: list[dict] = []
        for match in all_matches:
            tag = self._entity_tag(match)
            related_notes = self._find_notes_for_tag(notes, tag, max_notes=max_notes) if tag else []
            try:
                ddg_knowledge = ddg_futures[match["value"]].result()
            except Exception:
                ddg_knowledge = {}
            contexts.append({
                "type": match["type"],
                "type_label": self._entity_type_label(match["type"]),
                "value": match["value"],
                "mentions": match.get("mentions", 0),
                "image_url": match.get("image_url"),
                "tag": tag,
                "notes": related_notes,
                "ddg_knowledge": ddg_knowledge,
            })

        return contexts

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

    def _match_wuddai_entities(
        self,
        text: str,
        entities: list[dict],
        *,
        max_entities: int,
    ) -> list[dict]:
        index = {
            entity.get("value_normalized", ""): entity
            for entity in entities
            if entity.get("value_normalized")
        }
        if not index:
            return []

        candidate_scores: dict[str, tuple[int, dict]] = {}
        normalized_text = self._owner._normalize_entity_name(text)
        normalized_tokens = [
            token for token in normalized_text.split()
            if len(token) >= 3 and token not in _ENTITY_MATCH_STOPWORDS
        ]
        candidate_strings: set[str] = set()

        for raw_value, _label in self._extract_spacy_candidates(text):
            normalized = self._owner._normalize_entity_name(raw_value)
            if normalized:
                candidate_strings.add(normalized)

        for size in range(1, min(4, len(normalized_tokens)) + 1):
            for start in range(0, len(normalized_tokens) - size + 1):
                candidate_strings.add(" ".join(normalized_tokens[start:start + size]))

        padded_text = f" {normalized_text} "
        for key, entity in index.items():
            if f" {key} " in padded_text:
                candidate_scores[key] = (300 + int(entity.get("mentions", 0)), entity)

        for candidate in candidate_strings:
            if len(candidate) < 3:
                continue
            match = index.get(candidate)
            if match:
                score = 250 + int(match.get("mentions", 0))
                current = candidate_scores.get(candidate)
                if current is None or score > current[0]:
                    candidate_scores[candidate] = (score, match)
                continue

            if len(candidate) < 4 and " " not in candidate:
                continue

            for key, entity in index.items():
                if (candidate in key or key in candidate) and abs(len(candidate) - len(key)) <= 3:
                    score = 180 + min(len(candidate), len(key)) + int(entity.get("mentions", 0))
                    current = candidate_scores.get(key)
                    if current is None or score > current[0]:
                        candidate_scores[key] = (score, entity)

        ordered = sorted(
            candidate_scores.values(),
            key=lambda item: (-item[0], -int(item[1].get("mentions", 0)), item[1].get("value", "")),
        )
        return [entity for _score, entity in ordered[:max_entities]]

    def _build_entity_context(self, match: dict, notes: list[dict], *, max_notes: int) -> dict:
        tag = self._entity_tag(match)
        related_notes = self._find_notes_for_tag(notes, tag, max_notes=max_notes) if tag else []
        ddg_knowledge = self._fetch_ddg_entity_knowledge(match["value"])
        return {
            "type": match["type"],
            "type_label": self._entity_type_label(match["type"]),
            "value": match["value"],
            "mentions": match.get("mentions", 0),
            "image_url": match.get("image_url"),
            "tag": tag,
            "notes": related_notes,
            "ddg_knowledge": ddg_knowledge,
        }

    def _extract_fallback_entities(
        self,
        text: str,
        *,
        excluded_values: set[str],
        max_entities: int,
    ) -> list[dict]:
        if max_entities <= 0:
            return []

        fallback_entities: list[dict] = []
        seen_values = set(excluded_values)

        for raw_value, raw_label in self._extract_spacy_candidates(text):
            entity_type = self._map_fallback_label(raw_label, raw_value)
            if not entity_type:
                continue
            normalized = self._owner._normalize_entity_name(raw_value)
            if not normalized or normalized in seen_values:
                continue
            seen_values.add(normalized)
            fallback_entities.append(
                {
                    "value": raw_value.strip(),
                    "value_normalized": normalized,
                    "type": entity_type,
                    "mentions": 1,
                    "image_url": None,
                }
            )
            if len(fallback_entities) >= max_entities:
                return fallback_entities

        for product_name in self._extract_product_candidates(text):
            normalized = self._owner._normalize_entity_name(product_name)
            if not normalized or normalized in seen_values:
                continue
            seen_values.add(normalized)
            fallback_entities.append(
                {
                    "value": product_name,
                    "value_normalized": normalized,
                    "type": "PRODUCT",
                    "mentions": 1,
                    "image_url": None,
                }
            )
            if len(fallback_entities) >= max_entities:
                break

        return fallback_entities

    def _map_fallback_label(self, label: str, value: str) -> str | None:
        mapped = _FALLBACK_ENTITY_LABELS.get((label or "").upper())
        if mapped:
            return mapped
        if self._looks_like_product_name(value):
            return "PRODUCT"
        return None

    @classmethod
    def _extract_product_candidates(cls, text: str) -> list[str]:
        tokens = re.findall(r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9-]*", text or "")
        candidates: list[str] = []
        seen: set[str] = set()

        for start, token in enumerate(tokens):
            if not cls._is_product_lead_token(token):
                continue
            parts = [token]
            for next_token in tokens[start + 1:start + 4]:
                if cls._is_product_continuation_token(next_token):
                    parts.append(next_token)
                else:
                    break

            for size in range(len(parts), 0, -1):
                candidate = " ".join(parts[:size]).strip()
                if not cls._looks_like_product_name(candidate):
                    continue
                normalized = unicodedata.normalize("NFD", candidate.lower())
                normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
                if normalized in seen:
                    continue
                seen.add(normalized)
                candidates.append(candidate)
                break

        return candidates

    @classmethod
    def _looks_like_product_name(cls, value: str) -> bool:
        words = [word for word in re.split(r"\s+", (value or "").strip()) if word]
        if not words or len(words) > 4:
            return False

        if not cls._is_product_lead_token(words[0]):
            return False

        if len(words) == 1:
            return cls._token_has_product_signal(words[0])

        return all(cls._is_product_continuation_token(word) for word in words[1:])

    @classmethod
    def _is_product_lead_token(cls, token: str) -> bool:
        if not token:
            return False
        return cls._token_has_product_signal(token) or token[0].isupper()

    @classmethod
    def _is_product_continuation_token(cls, token: str) -> bool:
        if not token:
            return False
        return (
            cls._token_has_product_signal(token)
            or token[0].isupper()
            or token.isupper()
            or any(char.isdigit() for char in token)
        )

    @classmethod
    def _token_has_product_signal(cls, token: str) -> bool:
        lowered = unicodedata.normalize("NFD", token.lower())
        lowered = "".join(c for c in lowered if unicodedata.category(c) != "Mn")
        if lowered in _PRODUCT_HINT_TOKENS:
            return True
        has_inner_caps = any(char.isupper() for char in token[1:])
        has_digits = any(char.isdigit() for char in token)
        return has_inner_caps or has_digits

    def _entity_tag(self, entity: dict) -> str | None:
        entity_type = entity.get("type")
        official_value = entity.get("value")
        prefix = self._owner._wuddai_type_to_prefix().get(entity_type)
        if not prefix or not official_value:
            return None
        slug = re.sub(r"[^\w\s-]", "", self._owner._normalize_entity_name(official_value))
        slug = re.sub(r"[\s_]+", "-", slug)
        return f"{prefix}/{slug}" if slug else None

    def _list_notes(self) -> list[dict]:
        chroma = getattr(self._owner, "_chroma", None)
        if chroma is None:
            return []
        list_notes_sorted = getattr(chroma, "list_notes_sorted_by_title", None)
        if callable(list_notes_sorted):
            notes = list_notes_sorted()
            if isinstance(notes, list):
                return notes
        list_notes = getattr(chroma, "list_notes", None)
        if callable(list_notes):
            notes = list_notes()
            if isinstance(notes, list):
                return notes
        return []

    @staticmethod
    def _find_notes_for_tag(notes: list[dict], tag: str, *, max_notes: int) -> list[dict]:
        if not tag:
            return []
        target = tag.lower()
        matches: list[dict] = []
        for note in notes:
            note_tags = {item.lower() for item in note.get("tags", []) if item}
            if target not in note_tags:
                continue
            matches.append(
                {
                    "title": note.get("title") or Path(note.get("file_path", "")).stem or "(sans titre)",
                    "file_path": note.get("file_path", ""),
                    "date_modified": note.get("date_modified", ""),
                }
            )
            if len(matches) >= max_notes:
                break
        return matches

    @staticmethod
    def _entity_type_label(entity_type: str) -> str:
        return {
            "PERSON": "Personne",
            "ORG": "Organisation",
            "GPE": "Lieu",
            "LOC": "Lieu",
            "PRODUCT": "Produit",
            "EVENT": "Evenement",
            "NORP": "Groupe",
            "FAC": "Lieu",
        }.get(entity_type, entity_type.title())

    def _fetch_ddg_entity_knowledge(self, entity_name: str) -> dict:
        try:
            params = urllib.parse.urlencode(
                {
                    "q": entity_name,
                    "format": "json",
                    "no_html": "1",
                    "no_redirect": "1",
                    "skip_disambig": "0",
                }
            )
            request = urllib.request.Request(
                f"https://api.duckduckgo.com/?{params}",
                headers={"User-Agent": _DDG_USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=_DDG_TIMEOUT_SECONDS, context=_SSL_UNVERIFIED_CTX) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return self._summarize_ddg_entity_knowledge(payload)
        except Exception as exc:
            logger.debug(f"DDG knowledge lookup échoué pour {entity_name!r}: {exc}")
            return {}

    @classmethod
    def _summarize_ddg_entity_knowledge(cls, payload: dict) -> dict:
        if not payload:
            return {}

        summary = {
            "heading": (payload.get("Heading") or "").strip(),
            "entity": (payload.get("Entity") or "").strip(),
            "abstract_text": (payload.get("AbstractText") or "").strip(),
            "abstract_url": (payload.get("AbstractURL") or "").strip(),
            "abstract_source": (payload.get("AbstractSource") or "").strip(),
            "image": (payload.get("Image") or "").strip(),
            "answer": (payload.get("Answer") or "").strip(),
            "answer_type": (payload.get("AnswerType") or "").strip(),
            "definition": (payload.get("Definition") or "").strip(),
            "definition_url": (payload.get("DefinitionURL") or "").strip(),
            "definition_source": (payload.get("DefinitionSource") or "").strip(),
            "infobox": cls._extract_infobox(payload.get("Infobox") or {}),
            "related_topics": cls._extract_related_topics(payload.get("RelatedTopics") or []),
        }

        compact = {key: value for key, value in summary.items() if value}
        if not compact:
            return {}
        return compact

    @staticmethod
    def _extract_infobox(infobox: dict, *, max_entries: int = 8) -> list[dict]:
        entries: list[dict] = []
        for item in infobox.get("content") or []:
            label = str(item.get("label") or "").strip()
            value = str(item.get("value") or "").strip()
            wiki_order = item.get("wiki_order")
            if not label or not value:
                continue
            entries.append(
                {
                    "label": label,
                    "value": value,
                    "wiki_order": wiki_order,
                }
            )
            if len(entries) >= max_entries:
                break
        return entries

    @staticmethod
    def _extract_related_topics(items: list[dict], *, max_entries: int = 5) -> list[dict]:
        flattened: list[dict] = []

        def _walk(nodes: list[dict]) -> None:
            for node in nodes:
                text = str(node.get("Text") or "").strip()
                href = str(node.get("FirstURL") or "").strip()
                if text and href:
                    flattened.append({"text": text, "url": href})
                    if len(flattened) >= max_entries:
                        return
                topics = node.get("Topics")
                if isinstance(topics, list):
                    _walk(topics)
                    if len(flattened) >= max_entries:
                        return

        _walk(items)
        return flattened[:max_entries]