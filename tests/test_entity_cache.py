"""Tests unitaires pour src/learning/entity_cache.py (WuddaiCache, GeocodeCache)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.learning.entity_cache import GeocodeCache, WuddaiCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now():
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


def _normalize(text: str) -> str:
    return text.lower().strip().replace(".", "")


class _FakeUrlResponse:
    def __init__(self, payload: dict) -> None:
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _make_wuddai_cache(tmp_path: Path, wuddai_url: str = "http://localhost:5050") -> WuddaiCache:
    return WuddaiCache(
        data_dir=tmp_path / "data",
        utc_now_fn=_utc_now,
        normalize_fn=_normalize,
        wuddai_url=wuddai_url,
    )


def _make_geocode_cache(tmp_path: Path) -> GeocodeCache:
    return GeocodeCache(
        data_dir=tmp_path / "data",
        normalize_fn=_normalize,
    )


# ---------------------------------------------------------------------------
# WuddaiCache
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestWuddaiCache:
    def test_load_returns_fresh_cache_when_within_ttl(self, tmp_path):
        cache = _make_wuddai_cache(tmp_path)
        cache_file = tmp_path / "data" / "wuddai_entities_cache.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({
                "fetched_at": "2026-04-12T10:00:00+00:00",  # 2 h avant _utc_now
                "entities": [{"value": "Alice", "type": "PERSON", "value_normalized": "alice",
                               "mentions": 5, "image_url": None}],
            }),
            encoding="utf-8",
        )

        entities = cache.load()

        assert len(entities) == 1
        assert entities[0]["value"] == "Alice"

    def test_load_fetches_when_cache_expired(self, tmp_path):
        cache = _make_wuddai_cache(tmp_path)
        cache_file = tmp_path / "data" / "wuddai_entities_cache.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(
            json.dumps({
                "fetched_at": "2026-04-01T00:00:00+00:00",  # > 24 h
                "entities": [{"value": "Stale", "type": "ORG", "value_normalized": "stale",
                               "mentions": 0, "image_url": None}],
            }),
            encoding="utf-8",
        )
        payload = {"entities": [{"type": "PERSON", "value": "Bob", "mentions": 3,
                                  "image": {"url": "https://img/bob"}}]}

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            entities = cache.load()

        assert entities[0]["value"] == "Bob"
        assert entities[0]["value_normalized"] == "bob"
        assert entities[0]["image_url"] == "https://img/bob"

    def test_load_fetches_when_no_cache_file(self, tmp_path):
        cache = _make_wuddai_cache(tmp_path)
        payload = {"entities": [{"type": "ORG", "value": "OpenAI", "mentions": 10, "image": None}]}

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            entities = cache.load()

        assert entities[0]["value"] == "OpenAI"
        assert entities[0]["image_url"] is None

    def test_load_persists_fetched_data_to_disk(self, tmp_path):
        cache = _make_wuddai_cache(tmp_path)
        payload = {"entities": [{"type": "GPE", "value": "Paris", "mentions": 42, "image": None}]}
        (tmp_path / "data").mkdir(parents=True)

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            cache.load()

        saved = json.loads((tmp_path / "data" / "wuddai_entities_cache.json").read_text(encoding="utf-8"))
        assert saved["entities"][0]["value"] == "Paris"
        assert "fetched_at" in saved

    def test_load_returns_empty_list_on_network_error(self, tmp_path):
        cache = _make_wuddai_cache(tmp_path)

        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            entities = cache.load()

        assert entities == []

    def test_load_sets_value_normalized_via_normalize_fn(self, tmp_path):
        cache = _make_wuddai_cache(tmp_path)
        payload = {"entities": [{"type": "PERSON", "value": "Dupont", "mentions": 1, "image": None}]}

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            entities = cache.load()

        assert entities[0]["value_normalized"] == "dupont"


# ---------------------------------------------------------------------------
# GeocodeCache
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGeocodeCache:
    def test_get_coords_returns_cached_value(self, tmp_path):
        cache = _make_geocode_cache(tmp_path)
        cache_file = tmp_path / "data" / "geocode_cache.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({"paris": [48.8566, 2.3522]}), encoding="utf-8")

        coords = cache.get_coords("Paris")

        assert coords == (48.8566, 2.3522)

    def test_get_coords_returns_none_for_cached_null(self, tmp_path):
        cache = _make_geocode_cache(tmp_path)
        cache_file = tmp_path / "data" / "geocode_cache.json"
        cache_file.parent.mkdir(parents=True)
        cache_file.write_text(json.dumps({"inconnu": None}), encoding="utf-8")

        assert cache.get_coords("inconnu") is None

    def test_get_coords_queries_wikipedia_and_persists(self, tmp_path):
        cache = _make_geocode_cache(tmp_path)
        (tmp_path / "data").mkdir(parents=True)
        payload = {"query": {"pages": {"1": {"coordinates": [{"lat": 45.764, "lon": 4.8357}]}}}}

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            coords = cache.get_coords("Lyon")

        assert coords == (45.764, 4.8357)
        saved = json.loads((tmp_path / "data" / "geocode_cache.json").read_text(encoding="utf-8"))
        assert saved["lyon"] == [45.764, 4.8357]

    def test_get_coords_persists_none_when_not_found(self, tmp_path):
        cache = _make_geocode_cache(tmp_path)
        (tmp_path / "data").mkdir(parents=True)
        payload = {"query": {"pages": {"1": {"title": "Unknown"}}}}

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            coords = cache.get_coords("Nowhere")

        assert coords is None
        saved = json.loads((tmp_path / "data" / "geocode_cache.json").read_text(encoding="utf-8"))
        assert saved["nowhere"] is None

    def test_get_coords_tries_fr_then_en(self, tmp_path):
        cache = _make_geocode_cache(tmp_path)
        (tmp_path / "data").mkdir(parents=True)

        call_langs: list[str] = []

        def fake_urlopen(req, timeout=5):  # noqa: ANN001
            call_langs.append("fr" if "fr.wikipedia" in req.full_url else "en")
            if "fr.wikipedia" in req.full_url:
                raise OSError("no fr")
            return _FakeUrlResponse({"query": {"pages": {"1": {"coordinates": [{"lat": 1.0, "lon": 2.0}]}}}})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            coords = cache.get_coords("Testville")

        assert coords == (1.0, 2.0)
        assert call_langs == ["fr", "en"]

    def test_get_coords_returns_none_on_all_errors(self, tmp_path):
        cache = _make_geocode_cache(tmp_path)
        (tmp_path / "data").mkdir(parents=True)

        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            coords = cache.get_coords("Nowhere")

        assert coords is None
