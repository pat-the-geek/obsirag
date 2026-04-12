"""Sous-système autonome de cache pour les entités WUDD.ai et le géocodage GPE.

Ces classes ne dépendent d'aucun objet owner/AutoLearner : elles reçoivent leurs
dépendances (répertoire, fonctions utilitaires, URL) explicitement à la construction.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from loguru import logger

from src.storage.safe_read import read_json_file


class WuddaiCache:
    """Cache JSON local pour la liste d'entités WUDD.ai (TTL 24 h)."""

    def __init__(
        self,
        data_dir: Path,
        utc_now_fn: Callable[[], datetime],
        normalize_fn: Callable[[str], str],
        wuddai_url: str,
    ) -> None:
        self._data_dir = data_dir
        self._utc_now = utc_now_fn
        self._normalize = normalize_fn
        self._wuddai_url = wuddai_url
        self._cache_file = data_dir / "wuddai_entities_cache.json"

    def load(self) -> list[dict]:
        """Retourne la liste d'entités depuis le cache ou en la rafraîchissant."""
        if self._cache_file.exists():
            try:
                cached = read_json_file(self._cache_file, default={})
                fetched_at = datetime.fromisoformat(cached.get("fetched_at", "2000-01-01"))
                if fetched_at.tzinfo is None:
                    fetched_at = fetched_at.replace(tzinfo=UTC)
                if self._utc_now() - fetched_at < timedelta(hours=24):
                    return cached["entities"]
            except Exception:
                pass

        return self._fetch_and_store()

    def _fetch_and_store(self) -> list[dict]:
        try:
            import urllib.request

            url = f"{self._wuddai_url}/api/entities/export?limit=5000&images=true"
            req = urllib.request.Request(url, headers={"User-Agent": "ObsiRAG/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            entities = [
                {
                    "type": entity["type"],
                    "value": entity["value"],
                    "value_normalized": self._normalize(entity["value"]),
                    "mentions": entity.get("mentions", 0),
                    "image_url": entity.get("image", {}).get("url") if entity.get("image") else None,
                }
                for entity in data.get("entities", [])
            ]

            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps(
                    {"fetched_at": self._utc_now().isoformat(), "entities": entities},
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


class GeocodeCache:
    """Cache JSON persistent pour les coordonnées GPS des entités GPE (Wikipedia)."""

    def __init__(
        self,
        data_dir: Path,
        normalize_fn: Callable[[str], str],
    ) -> None:
        self._data_dir = data_dir
        self._normalize = normalize_fn
        self._cache_file = data_dir / "geocode_cache.json"

    def get_coords(self, entity_name: str) -> tuple[float, float] | None:
        """Retourne (lat, lon) depuis le cache ou en interrogeant l'API Wikipedia."""
        try:
            cache: dict = read_json_file(self._cache_file, default={}) if self._cache_file.exists() else {}
        except Exception:
            cache = {}

        key = self._normalize(entity_name)
        if key in cache:
            return tuple(cache[key]) if cache[key] else None  # type: ignore[return-value]

        coords = self._lookup_wikipedia(entity_name)

        cache[key] = list(coords) if coords else None
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        return coords

    def _lookup_wikipedia(self, entity_name: str) -> tuple[float, float] | None:
        import urllib.parse
        import urllib.request

        for lang in ("fr", "en"):
            try:
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
                        return (coordinates[0]["lat"], coordinates[0]["lon"])
            except Exception:
                pass
        return None
