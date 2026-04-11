from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.learning.entity_services import AutoLearnEntityServices


class _FakeUrlResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, *_args, **_kwargs):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_owner(tmp_settings):
    owner = MagicMock()
    owner._get_settings.return_value = tmp_settings
    owner._utc_now.return_value = datetime.fromisoformat("2026-04-11T12:00:00+00:00")
    owner._normalize_entity_name.side_effect = lambda text: text.lower().strip().replace(".", "")
    owner._wuddai_type_to_prefix.return_value = {
        "PERSON": "personne",
        "ORG": "org",
        "GPE": "lieu",
        "LOC": "lieu",
        "PRODUCT": "produit",
    }
    owner._wuddai_image_types.return_value = ["PERSON", "ORG", "GPE", "PRODUCT"]
    return owner


@pytest.mark.unit
class TestEntityServices:
    def test_load_wuddai_entities_uses_fresh_cache_when_available(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        cache_file = tmp_settings.data_dir / "wuddai_entities_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({
                "fetched_at": "2026-04-11T10:00:00+00:00",
                "entities": [{"value": "Alice", "value_normalized": "alice", "type": "PERSON", "mentions": 1, "image_url": None}],
            }),
            encoding="utf-8",
        )

        entities = AutoLearnEntityServices(owner).load_wuddai_entities()

        assert entities[0]["value"] == "Alice"

    def test_extract_validated_entities_falls_back_to_owner_spacy_helper(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        owner._load_wuddai_entities.return_value = []
        owner._entities_to_tags_spacy.return_value = ["personne/alice"]

        tags, images = AutoLearnEntityServices(owner).extract_validated_entities("Alice visite Paris")

        assert tags == ["personne/alice"]
        assert images == []

    def test_build_entity_image_gallery_keeps_first_entity_per_type(self):
        gallery = AutoLearnEntityServices.build_entity_image_gallery([
            {"type": "ORG", "value": "OpenAI", "image_url": "https://img/openai"},
            {"type": "PERSON", "value": "Alice", "image_url": "https://img/alice"},
            {"type": "ORG", "value": "Other Org", "image_url": "https://img/other"},
        ])

        assert "![Alice](https://img/alice)" in gallery
        assert "![OpenAI](https://img/openai)" in gallery
        assert "Other Org" not in gallery

    def test_fetch_gpe_coordinates_uses_cache_then_persists_lookup(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        service = AutoLearnEntityServices(owner)
        cache_file = tmp_settings.data_dir / "geocode_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"paris": [48.8566, 2.3522]}), encoding="utf-8")

        assert service.fetch_gpe_coordinates("Paris") == (48.8566, 2.3522)

        cache_file.write_text("{}", encoding="utf-8")
        payload = {"query": {"pages": {"1": {"coordinates": [{"lat": 45.764, "lon": 4.8357}]}}}}
        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)):
            coords = service.fetch_gpe_coordinates("Lyon")

        assert coords == (45.764, 4.8357)
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        assert saved["lyon"] == [45.764, 4.8357]