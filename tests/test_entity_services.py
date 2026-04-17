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

    def test_summarize_ddg_entity_knowledge_extracts_core_fields(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        service = AutoLearnEntityServices(owner)

        summary = service._summarize_ddg_entity_knowledge(
            {
                "Heading": "Ada Lovelace",
                "AbstractText": "English mathematician.",
                "AbstractURL": "https://en.wikipedia.org/wiki/Ada_Lovelace",
                "Infobox": {
                    "content": [
                        {"label": "Born", "value": "1815"},
                        {"label": "Known for", "value": "Analytical Engine"},
                    ]
                },
                "RelatedTopics": [
                    {"Text": "Charles Babbage - English polymath", "FirstURL": "https://duckduckgo.com/Charles_Babbage"}
                ],
            }
        )

        assert summary["heading"] == "Ada Lovelace"
        assert summary["abstract_text"] == "English mathematician."
        assert summary["infobox"][0]["label"] == "Born"
        assert summary["related_topics"][0]["url"] == "https://duckduckgo.com/Charles_Babbage"

    def test_lookup_wuddai_entity_contexts_returns_notes_and_ddg_knowledge(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        owner._load_wuddai_entities.return_value = [
            {
                "value": "Ada Lovelace",
                "value_normalized": "ada lovelace",
                "type": "PERSON",
                "mentions": 12,
                "image_url": "https://img/ada.png",
            }
        ]
        owner._chroma = MagicMock()
        owner._chroma.list_notes_sorted_by_title.return_value = [
            {
                "title": "Ada Notes",
                "file_path": "People/Ada.md",
                "date_modified": "2026-04-16",
                "tags": ["personne/ada-lovelace"],
            }
        ]
        service = AutoLearnEntityServices(owner)

        with patch.object(service, "_extract_spacy_candidates", return_value=[("Ada Lovelace", "PERSON")]):
            with patch.object(service, "_fetch_ddg_entity_knowledge", return_value={"abstract_text": "English mathematician."}):
                contexts = service.lookup_wuddai_entity_contexts("Qui est Ada Lovelace ?")

        assert len(contexts) == 1
        assert contexts[0]["value"] == "Ada Lovelace"
        assert contexts[0]["tag"] == "personne/ada-lovelace"
        assert contexts[0]["notes"][0]["file_path"] == "People/Ada.md"
        assert contexts[0]["ddg_knowledge"]["abstract_text"] == "English mathematician."

    def test_lookup_wuddai_entity_contexts_ignores_short_stopword_false_positives(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        owner._load_wuddai_entities.return_value = [
            {
                "value": "Ada Lovelace",
                "value_normalized": "ada lovelace",
                "type": "PERSON",
                "mentions": 12,
                "image_url": "https://img/ada.png",
            },
            {
                "value": "Best Buy",
                "value_normalized": "best buy",
                "type": "ORG",
                "mentions": 26,
                "image_url": "https://img/bestbuy.png",
            },
        ]
        owner._chroma = MagicMock()
        owner._chroma.list_notes_sorted_by_title.return_value = []
        service = AutoLearnEntityServices(owner)

        with patch.object(service, "_extract_spacy_candidates", return_value=[("Ada Lovelace", "PERSON")]):
            with patch.object(service, "_fetch_ddg_entity_knowledge", return_value={}):
                contexts = service.lookup_wuddai_entity_contexts("Qui est Ada Lovelace ?")

        assert [context["value"] for context in contexts] == ["Ada Lovelace"]

    def test_lookup_wuddai_entity_contexts_adds_product_fallback_when_missing_from_wuddai(self, tmp_settings):
        owner = _make_owner(tmp_settings)
        owner._load_wuddai_entities.return_value = []
        owner._chroma = MagicMock()
        owner._chroma.list_notes_sorted_by_title.return_value = []
        service = AutoLearnEntityServices(owner)

        with patch.object(service, "_extract_spacy_candidates", return_value=[]):
            with patch.object(service, "_fetch_ddg_entity_knowledge", return_value={}):
                contexts = service.lookup_wuddai_entity_contexts("Compare le MacBook Neo au MacBook Air")

        assert [context["value"] for context in contexts] == ["MacBook Neo", "MacBook Air"]
        assert [context["type"] for context in contexts] == ["PRODUCT", "PRODUCT"]
        assert contexts[0]["tag"] == "produit/macbook-neo"