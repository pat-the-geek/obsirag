from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import json
import os
import threading
import sys

import pytest

from src.learning.autolearn import AutoLearner, _normalize_entity_name


class _FakeUrlResponse:
    def __init__(self, payload, headers=None):
        if isinstance(payload, dict):
            self._payload = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, bytes):
            self._payload = payload
        else:
            self._payload = str(payload).encode("utf-8")
        self.headers = headers or {}

    def read(self, *_args, **_kwargs):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeThread:
    def __init__(self, target=None, daemon=None, name=None):
        self.target = target
        self.daemon = daemon
        self.name = name
        self.started = False

    def start(self):
        self.started = True


@pytest.mark.unit
class TestAutoLearner:
    def test_start_schedules_cycle_and_weekly_jobs_when_not_first_run(self, tmp_settings):
        chroma = MagicMock()
        rag = MagicMock()
        indexer = MagicMock()

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner = AutoLearner(chroma, rag, indexer)
            learner._scheduler = MagicMock()
            learner._scheduler.running = False

            with patch.object(learner, "_is_first_insight_run", return_value=False):
                learner.start()

        assert learner._scheduler.add_job.call_count == 2
        learner._scheduler.start.assert_called_once()

    def test_run_cycle_skips_outside_active_hours(self, tmp_settings):
        chroma = MagicMock()
        rag = MagicMock()
        indexer = MagicMock()
        tmp_settings.autolearn_active_hour_start = 8
        tmp_settings.autolearn_active_hour_end = 22

        class _LateNight(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 4, 11, 2, 0, 0)

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner = AutoLearner(chroma, rag, indexer)
            with patch("src.learning.autolearn.datetime", _LateNight):
                learner._run_cycle()

        rag._llm.load.assert_not_called()
        chroma.search.assert_not_called()

    def test_run_cycle_processes_recent_and_fullscan_notes(self, tmp_settings):
        chroma = MagicMock()
        chroma.get_recently_modified.return_value = [
            {"file_path": "recent.md", "title": "Recent"},
        ]
        chroma.list_user_notes.return_value = [
            {"file_path": "recent.md", "title": "Recent"},
            {"file_path": "older.md", "title": "Older"},
        ]
        chroma.list_notes.return_value = [
            {"file_path": "recent.md", "title": "Recent"},
            {"file_path": "older.md", "title": "Older"},
            {"file_path": "obsirag/insights/skip.md", "title": "Skip"},
        ]
        rag = MagicMock()
        indexer = MagicMock()

        tmp_settings.autolearn_active_hour_start = 0
        tmp_settings.autolearn_active_hour_end = 24
        tmp_settings.autolearn_max_notes_per_run = 2
        tmp_settings.autolearn_fullscan_per_run = 2
        tmp_settings.autolearn_lookback_hours = 24
        tmp_settings.autolearn_min_reprocess_days = 7

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner = AutoLearner(chroma, rag, indexer)
            with (
                patch.object(learner, "_load_processed", return_value={}),
                patch.object(learner, "_process_note") as process_note,
                patch.object(learner, "_mark_processed") as mark_processed,
                patch.object(learner, "_discover_synapses") as discover_synapses,
                patch.object(learner, "_record_processing_time"),
                patch.object(learner, "_wait_for_idle"),
                patch("src.learning.autolearn.time.sleep"),
            ):
                learner._run_cycle()

        rag._llm.load.assert_called_once()
        chroma.search.assert_called_once_with("warm-up", top_k=1)
        assert process_note.call_count == 2
        mark_processed.assert_any_call("recent.md")
        mark_processed.assert_any_call("older.md")
        discover_synapses.assert_called_once_with([
            {"file_path": "recent.md", "title": "Recent"},
            {"file_path": "older.md", "title": "Older"},
        ])
        assert learner.processing_status["active"] is False

    def test_process_note_saves_artifact_when_answer_is_strong(self):
        chroma = MagicMock()
        chroma.search.return_value = [
            {"text": "Extrait 1", "metadata": {"file_path": "note.md"}},
            {"text": "Extrait 2", "metadata": {"file_path": "note.md"}},
        ]
        rag = MagicMock()
        rag.query.return_value = ("Réponse RAG suffisamment longue pour être gardée.", [
            {"metadata": {"file_path": "note.md"}},
        ])
        rag._llm.chat.return_value = (
            "Réponse enrichie suffisamment longue pour dépasser le seuil minimal et éviter "
            "la détection de réponse faible dans le test."
        )
        indexer = MagicMock()
        learner = AutoLearner(chroma, rag, indexer)

        note_meta = {"file_path": "note.md", "title": "Note test", "tags": ["tag1"]}

        with (
            patch.object(learner, "_generate_questions", return_value=["Quelle question ?"]),
            patch.object(learner, "_web_search", return_value=[{"body": "Contenu web", "href": "https://example.com", "title": "Example"}]),
            patch.object(learner, "_snippets_relevant", return_value=True),
            patch.object(learner, "_is_weak_answer", return_value=False),
            patch.object(learner, "_save_knowledge_artifact") as save_artifact,
            patch.object(learner, "_set_status"),
        ):
            learner._process_note(note_meta, sleep_between_questions=0)

        save_artifact.assert_called_once()

    def test_process_note_skips_artifact_when_no_valid_answer(self):
        chroma = MagicMock()
        chroma.search.return_value = [
            {"text": "Extrait 1", "metadata": {"file_path": "note.md"}},
        ]
        rag = MagicMock()
        rag.query.return_value = ("trop court", [])
        indexer = MagicMock()
        learner = AutoLearner(chroma, rag, indexer)

        note_meta = {"file_path": "note.md", "title": "Note test", "tags": []}

        with (
            patch.object(learner, "_generate_questions", return_value=["Quelle question ?"]),
            patch.object(learner, "_web_search", return_value=[]),
            patch.object(learner, "_save_knowledge_artifact") as save_artifact,
            patch.object(learner, "_set_status"),
        ):
            learner._process_note(note_meta, sleep_between_questions=0)

        save_artifact.assert_not_called()

    def test_normalize_entity_name_strips_accents_punctuation_and_spaces(self):
        assert _normalize_entity_name("  Montréal, QC!  ") == "montreal qc"
        assert _normalize_entity_name("Crème brûlée") == "creme brulee"
        assert _normalize_entity_name("   ") == ""

    def test_is_obsirag_generated_detects_internal_artifacts(self):
        assert AutoLearner._is_obsirag_generated("obsirag/insights/test.md") is True
        assert AutoLearner._is_obsirag_generated("vault/obsirag/synthesis/test.md") is True
        assert AutoLearner._is_obsirag_generated("notes/source.md") is False

    def test_is_weak_answer_detects_short_and_known_insufficient_patterns(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        assert learner._is_weak_answer("trop court") is True
        assert learner._is_weak_answer("Je ne sais pas répondre à cette question à partir des notes fournies.") is True
        assert learner._is_weak_answer("x" * 151) is False

    def test_fit_context_applies_split_budget_and_security_floor(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        tmp_settings.ollama_context_size = 200
        rag_ctx = "R" * 400
        web_ctx = "W" * 900

        with patch("src.learning.autolearn.settings", tmp_settings):
            fitted_rag, fitted_web = learner._fit_context(rag_ctx, web_ctx, overhead=100)

        assert len(fitted_rag) == 240
        assert len(fitted_web) == 560

    def test_snippets_relevant_uses_question_keywords_and_handles_empty_question(self):
        assert AutoLearner._snippets_relevant(
            "Quels sont les impacts climatiques mesurables du transport maritime ?",
            ["Le transport maritime a des impacts climatiques mesurables."]
        ) is True
        assert AutoLearner._snippets_relevant(
            "Quels sont les impacts climatiques mesurables du transport maritime ?",
            ["Recette de cuisine et jardinage domestique."]
        ) is False
        assert AutoLearner._snippets_relevant("quoi", ["un snippet existe"]) is True

    def test_load_processed_returns_empty_when_file_missing_or_invalid(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._load_processed() == {}
            tmp_settings.processed_notes_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_settings.processed_notes_file.write_text("{broken", encoding="utf-8")
            assert learner._load_processed() == {}

    def test_save_processed_writes_json_atomically(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        processed = {"note.md": "2026-04-11T12:00:00"}

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner._save_processed(processed)

        saved = json.loads(tmp_settings.processed_notes_file.read_text(encoding="utf-8"))
        assert saved == processed
        leftovers = list(tmp_settings.processed_notes_file.parent.glob("*.tmp"))
        assert leftovers == []

    def test_save_processed_cleans_temp_file_when_replace_fails(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        temp_paths: list[str] = []

        def _fake_mkstemp(dir=None, suffix=""):
            path = os.path.join(dir, f"manual{suffix}")
            fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600)
            temp_paths.append(path)
            return fd, path

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.autolearn.tempfile.mkstemp", side_effect=_fake_mkstemp),
            patch("src.learning.autolearn.os.replace", side_effect=OSError("replace failed")),
        ):
            with pytest.raises(OSError):
                learner._save_processed({"note.md": "x"})

        assert temp_paths
        assert not os.path.exists(temp_paths[0])

    def test_frontmatter_helpers_handle_missing_and_existing_blocks(self):
        content = "---\ntags:\n  - alpha\n  - beta\nsummary: test\n---\nBody"

        end = AutoLearner._fm_end(content)

        assert end > 0
        assert AutoLearner._read_frontmatter_tags(content) == ["alpha", "beta"]
        merged = AutoLearner._merge_frontmatter_tags(content, ["beta", "gamma"])
        assert "  - alpha" in merged
        assert "  - beta" in merged
        assert "  - gamma" in merged
        assert AutoLearner._fm_end("No frontmatter") == -1

    def test_add_location_to_frontmatter_creates_or_replaces_location(self):
        content = "---\ntitle: Test\nlocation: [1.000000, 2.000000]\n---\nBody"

        updated = AutoLearner._add_location_to_frontmatter(content, 48.8566, 2.3522)
        created = AutoLearner._add_location_to_frontmatter("Body only", 45.0, 7.0)

        assert updated.count("location:") == 1
        assert "location: [48.856600, 2.352200]" in updated
        assert created.startswith("---\nlocation: [45.000000, 7.000000]\n---\nBody only")

    def test_synapse_pair_key_is_order_independent(self):
        assert AutoLearner._synapse_pair_key("b.md", "a.md") == "a.md|||b.md"

    def test_find_existing_insight_matches_by_title_prefix_and_ner_overlap(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        dated_dir = tmp_settings.insights_dir / "2026-04"
        dated_dir.mkdir(parents=True, exist_ok=True)
        exact = dated_dir / "Note_Test_20260411.md"
        exact.write_text("---\ntags:\n  - person/alice\n  - org/acme\n---\nBody", encoding="utf-8")
        thematic = dated_dir / "Other.md"
        thematic.write_text("---\ntags:\n  - person/alice\n  - org/acme\n  - lieu/paris\n---\nBody", encoding="utf-8")

        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._find_existing_insight("Note Test", ["person/alice"]) == exact
            assert learner._find_existing_insight("Unknown", ["person/alice", "org/acme"]) == thematic
            assert learner._find_existing_insight("Unknown", ["person/alice"]) is None

    def test_find_existing_insight_uses_chroma_insight_listing_when_available(self, tmp_settings):
        chroma = MagicMock()
        chroma.list_insight_notes.return_value = [{"file_path": "obsirag/insights/2026-04/Note_Test_20260411.md"}]
        learner = AutoLearner(chroma, MagicMock(), MagicMock())
        learner._metrics = MagicMock()
        dated_dir = tmp_settings.insights_dir / "2026-04"
        dated_dir.mkdir(parents=True, exist_ok=True)
        exact = dated_dir / "Note_Test_20260411.md"
        exact.write_text("---\ntags:\n  - person/alice\n---\nBody", encoding="utf-8")

        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._find_existing_insight("Note Test", ["person/alice"]) == exact
        learner._metrics.increment.assert_not_called()

    def test_find_existing_insight_records_rglob_fallback_metrics_when_index_and_shallow_glob_miss(self, tmp_settings):
        chroma = MagicMock()
        chroma.list_insight_notes.return_value = []
        learner = AutoLearner(chroma, MagicMock(), MagicMock())
        learner._metrics = MagicMock()

        deep_dir = tmp_settings.insights_dir / "legacy" / "nested"
        deep_dir.mkdir(parents=True, exist_ok=True)
        deep_candidate = deep_dir / "Note_Test_20260411.md"
        deep_candidate.write_text("---\ntags:\n  - person/alice\n---\nBody", encoding="utf-8")

        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._find_existing_insight("Note Test", ["person/alice"]) == deep_candidate

        learner._metrics.increment.assert_any_call("autolearn_fs_fallback_insight_glob_total")
        learner._metrics.increment.assert_any_call("autolearn_fs_fallback_insight_rglob_total")

    def test_find_existing_insight_skips_frontmatter_read_when_title_prefix_matches(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        dated_dir = tmp_settings.insights_dir / "2026-04"
        dated_dir.mkdir(parents=True, exist_ok=True)
        exact = dated_dir / "Note_Test_20260411.md"
        exact.write_text("---\ntags:\n  - person/alice\n---\nBody", encoding="utf-8")

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.artifact_writer.read_text_file", side_effect=AssertionError("should not be called")),
        ):
            assert learner._find_existing_insight("Note Test", ["person/alice", "org/acme"]) == exact

    def test_append_to_insight_updates_metadata_and_archives_when_too_large(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        tmp_settings.max_insight_size_bytes = 80
        path = tmp_settings.insights_dir / "2026-04" / "Insight.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntags:\n  - insight\n---\n# Insights\n\n**Générée le :** old\n\n## Question 1\n\n> Q\n\nA\n",
            encoding="utf-8",
        )
        qa_pairs = [{
            "question": "Q2 ?",
            "answer": "Réponse longue pour dépasser la taille limite et forcer l'archivage.",
            "sources": ["note.md"],
            "web_refs": [{"title": "Ref", "url": "https://example.com"}],
        }]

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_fetch_gpe_coordinates", return_value=(48.0, 2.0)),
            patch.object(learner, "_synthesize_web_sources", return_value="Synthèse"),
            patch.object(learner, "_build_entity_image_gallery", return_value="![img](x)"),
        ):
            learner._append_to_insight(
                path,
                qa_pairs,
                ["person/alice", "org/acme"],
                "Web",
                entity_images=[{"type": "GPE", "value": "Paris"}],
            )

        archived = list(path.parent.glob("Insight_archive_*.md"))
        assert len(archived) == 1
        content = archived[0].read_text(encoding="utf-8")
        assert "Mise à jour le" in content
        assert "location: [48.000000, 2.000000]" in content
        assert "## Entités clés" in content
        assert "## Question 2" in content

    def test_save_knowledge_artifact_appends_to_existing_match(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        note_meta = {"file_path": "note.md", "tags": ["source"]}
        qa_pairs = [{"question": "Q?", "answer": "A", "sources": ["note.md"], "provenance": "Web"}]
        existing = tmp_settings.insights_dir / "2026-04" / "existing.md"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_text("stub", encoding="utf-8")

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_extract_validated_entities", return_value=(["person/alice"], [])),
            patch.object(learner, "_find_existing_insight", return_value=existing),
            patch.object(learner, "_append_to_insight") as append_to_insight,
        ):
            learner._save_knowledge_artifact("Note Test", note_meta, qa_pairs)

        append_to_insight.assert_called_once_with(existing, qa_pairs, ["person/alice"], "Web", [])

    def test_save_knowledge_artifact_creates_new_file_with_combined_provenance(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        note_meta = {"file_path": "folder/note.md", "tags": ["source"]}
        qa_pairs = [
            {"question": "Q1?", "answer": "A1", "sources": ["folder/note.md"], "provenance": "Coffre"},
            {"question": "Q2?", "answer": "A2", "sources": ["folder/other.md"], "provenance": "Web"},
        ]

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_extract_validated_entities", return_value=(["person/alice"], [])),
            patch.object(learner, "_find_existing_insight", return_value=None),
            patch.object(learner, "_build_entity_image_gallery", return_value=""),
            patch.object(learner, "_synthesize_web_sources", return_value=""),
        ):
            learner._save_knowledge_artifact("Note Test", note_meta, qa_pairs)

        created = list((tmp_settings.insights_dir / "2026-04").glob("Note_Test_*.md"))
        assert len(created) == 1
        content = created[0].read_text(encoding="utf-8")
        assert "**Provenance :** Coffre et Web" in content
        assert "[[folder/note]]" in content
        assert "[[folder/other]]" in content

    def test_load_and_save_synapse_index_round_trip(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._load_synapse_index() == set()
            learner._save_synapse_index({"b|||a", "a|||c"})
            assert learner._load_synapse_index() == {"a|||c", "b|||a"}

    def test_discover_synapses_returns_early_when_quota_is_zero(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        tmp_settings.autolearn_synapse_per_run = 0

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner._discover_synapses([{"file_path": "a.md", "wikilinks": []}])

        learner._chroma.find_similar_notes.assert_not_called()

    def test_discover_synapses_skips_existing_pairs_and_saves_new_ones(self, tmp_settings):
        chroma = MagicMock()
        chroma.find_similar_notes.side_effect = [
            [{"file_path": "b.md", "title": "B", "score": 0.9, "excerpt": "..."}, {"file_path": "c.md", "title": "C", "score": 0.8, "excerpt": "..."}],
            [],
        ]
        learner = AutoLearner(chroma, MagicMock(), MagicMock())
        tmp_settings.autolearn_synapse_per_run = 2
        notes = [
            {"file_path": "a.md", "title": "A", "wikilinks": []},
            {"file_path": "b.md", "title": "B", "wikilinks": []},
        ]

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_load_synapse_index", return_value={"a.md|||b.md"}),
            patch.object(learner, "_save_synapse_index") as save_synapse_index,
            patch.object(learner, "_create_synapse_artifact") as create_synapse_artifact,
            patch("src.learning.autolearn.time.sleep"),
            patch("random.shuffle", side_effect=lambda items: None),
        ):
            learner._discover_synapses(notes)

        create_synapse_artifact.assert_called_once()
        created_args = create_synapse_artifact.call_args[0]
        assert created_args[0]["file_path"] == "a.md"
        assert created_args[1]["file_path"] == "c.md"
        save_synapse_index.assert_called_once()

    def test_extract_validated_entities_falls_back_to_spacy_when_wuddai_is_unavailable(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with (
            patch.object(learner, "_load_wuddai_entities", return_value=[]),
            patch.object(learner, "_entities_to_tags_spacy", return_value=["personne/alice"]),
        ):
            tags, images = learner._extract_validated_entities("Alice visite Paris")

        assert tags == ["personne/alice"]
        assert images == []

    def test_extract_validated_entities_matches_exact_and_partial_wuddai_entries(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        entities = [
            {"value_normalized": "alice", "value": "Alice", "type": "PERSON", "image_url": "https://img/alice", "mentions": 2},
            {"value_normalized": "openai inc", "value": "OpenAI Inc.", "type": "ORG", "image_url": "https://img/openai", "mentions": 5},
            {"value_normalized": "paris", "value": "Paris", "type": "GPE", "image_url": "https://img/paris", "mentions": 3},
            {"value_normalized": "ignored", "value": "Ignored", "type": "DATE", "image_url": "https://img/ignored", "mentions": 10},
        ]
        fake_doc = SimpleNamespace(ents=[
            SimpleNamespace(text="Alice", label_="PER"),
            SimpleNamespace(text="OpenAI", label_="ORG"),
            SimpleNamespace(text="Paris", label_="LOC"),
            SimpleNamespace(text="Alice", label_="PER"),
        ])

        with (
            patch.object(learner, "_load_wuddai_entities", return_value=entities),
            patch("src.vault.parser.get_nlp", return_value=lambda text: fake_doc),
        ):
            tags, images = learner._extract_validated_entities("Alice OpenAI Paris")

        assert tags == ["personne/alice", "org/openai-inc", "lieu/paris"]
        assert [img["type"] for img in images] == ["PERSON", "ORG", "GPE"]

    def test_entities_to_tags_spacy_maps_supported_labels_and_deduplicates(self):
        fake_doc = SimpleNamespace(ents=[
            SimpleNamespace(text="Alice", label_="PER"),
            SimpleNamespace(text="OpenAI", label_="ORG"),
            SimpleNamespace(text="Paris", label_="GPE"),
            SimpleNamespace(text="Paris", label_="LOC"),
            SimpleNamespace(text="12", label_="CARDINAL"),
        ])

        with patch("src.vault.parser.get_nlp", return_value=lambda text: fake_doc):
            tags = AutoLearner._entities_to_tags_spacy("Alice OpenAI Paris")

        assert tags == ["personne/alice", "org/openai", "lieu/paris"]

    def test_build_entity_image_gallery_prioritizes_first_entity_per_type(self):
        gallery = AutoLearner._build_entity_image_gallery([
            {"type": "ORG", "value": "OpenAI", "image_url": "https://img/openai"},
            {"type": "PERSON", "value": "Alice", "image_url": "https://img/alice"},
            {"type": "ORG", "value": "Other Org", "image_url": "https://img/other"},
            {"type": "GPE", "value": "Paris", "image_url": "https://img/paris"},
        ])

        assert "![Alice](https://img/alice)" in gallery
        assert "![OpenAI](https://img/openai)" in gallery
        assert "![Other Org](https://img/other)" not in gallery
        assert AutoLearner._build_entity_image_gallery([]) == ""

    def test_create_synapse_artifact_writes_markdown_file(self, tmp_settings):
        chroma = MagicMock()
        chroma.search.return_value = [{"text": "Extrait de la note A"}]
        rag = MagicMock()
        rag._llm.chat.return_value = "Connexion implicite entre les deux notes."
        learner = AutoLearner(chroma, rag, MagicMock())

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner._create_synapse_artifact(
                {"file_path": "a.md", "title": "Note A"},
                {"file_path": "b.md", "title": "Note B", "score": 0.83, "excerpt": "Extrait B"},
            )

        created = list(tmp_settings.synapses_dir.glob("Note_A__Note_B_*.md"))
        assert len(created) == 1
        content = created[0].read_text(encoding="utf-8")
        assert "# Synapse : Note A ↔ Note B" in content
        assert "**Similarité sémantique :** 83%" in content
        assert "Connexion implicite entre les deux notes." in content

    def test_suggest_note_title_filters_keep_long_non_latin_and_same_title(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        learner._rag._llm.chat.side_effect = [
            "CONSERVER",
            "x" * 81,
            "タイトル",
            "Titre actuel",
            "Nouveau titre",
        ]

        assert learner._suggest_note_title("contenu", "Titre actuel") is None
        assert learner._suggest_note_title("contenu", "Titre actuel") is None
        assert learner._suggest_note_title("contenu", "Titre actuel") is None
        assert learner._suggest_note_title("contenu", "Titre actuel") is None
        assert learner._suggest_note_title("contenu", "Titre actuel") == "Nouveau titre"

    def test_rename_note_in_vault_updates_frontmatter_links_and_processed_map(self, tmp_settings):
        vault = tmp_settings.vault
        note = vault / "Old Title.md"
        note.write_text("---\ntags:\n  - x\n---\nBody", encoding="utf-8")
        linked = vault / "Linked.md"
        linked.write_text("Lien [[Old Title]] et [[Old Title|alias]]", encoding="utf-8")
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        processed = {"Old Title.md": "2026-04-11T10:00:00"}

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_load_processed", return_value=processed.copy()),
            patch.object(learner, "_save_processed") as save_processed,
        ):
            new_abs = learner._rename_note_in_vault(note, "New Title", "Old Title.md")

        assert new_abs is not None
        assert new_abs.name == "New Title.md"
        new_content = new_abs.read_text(encoding="utf-8")
        assert "title: New Title" in new_content
        assert "[[New Title]]" in linked.read_text(encoding="utf-8")
        learner._indexer.index_note.assert_any_call(linked)
        learner._indexer.index_note.assert_any_call(new_abs)
        save_processed.assert_called_once()

    def test_load_wuddai_entities_uses_fresh_cache_when_available(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        cache_file = tmp_settings.data_dir / "wuddai_entities_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({
                "fetched_at": "2026-04-11T10:00:00+00:00",
                "entities": [{"value": "Alice", "value_normalized": "alice", "type": "PERSON", "mentions": 1, "image_url": None}],
            }),
            encoding="utf-8",
        )

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.autolearn._utc_now", return_value=datetime.fromisoformat("2026-04-11T12:00:00+00:00")),
        ):
            entities = learner._load_wuddai_entities()

        assert entities[0]["value"] == "Alice"

    def test_load_wuddai_entities_fetches_and_persists_when_cache_is_stale(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        cache_file = tmp_settings.data_dir / "wuddai_entities_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"fetched_at": "2026-04-01T10:00:00+00:00", "entities": []}), encoding="utf-8")
        payload = {
            "entities": [
                {"type": "PERSON", "value": "Alice", "mentions": 2, "image": {"url": "https://img/alice"}},
                {"type": "ORG", "value": "OpenAI", "mentions": 3, "image": None},
            ]
        }

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.autolearn._utc_now", return_value=datetime.fromisoformat("2026-04-11T12:00:00+00:00")),
            patch("urllib.request.urlopen", return_value=_FakeUrlResponse(payload)),
        ):
            entities = learner._load_wuddai_entities()

        assert entities[0]["value_normalized"] == "alice"
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        assert len(saved["entities"]) == 2

    def test_load_wuddai_entities_returns_empty_and_warns_on_fetch_error(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("urllib.request.urlopen", side_effect=OSError("offline")),
            patch("src.learning.autolearn.logger.warning") as warning,
        ):
            entities = learner._load_wuddai_entities()

        assert entities == []
        warning.assert_called_once()

    def test_fetch_gpe_coordinates_uses_cache_and_persists_fetch_result(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        cache_file = tmp_settings.data_dir / "geocode_cache.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"paris": [48.8566, 2.3522]}), encoding="utf-8")

        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._fetch_gpe_coordinates("Paris") == (48.8566, 2.3522)

        cache_file.write_text("{}", encoding="utf-8")
        payload = {"query": {"pages": {"1": {"coordinates": [{"lat": 45.764, "lon": 4.8357}]}}}}

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("urllib.request.urlopen", side_effect=[_FakeUrlResponse(payload)]),
        ):
            coords = learner._fetch_gpe_coordinates("Lyon")

        assert coords == (45.764, 4.8357)
        saved = json.loads(cache_file.read_text(encoding="utf-8"))
        assert saved["lyon"] == [45.764, 4.8357]

    def test_weekly_synthesis_writes_file_and_skips_when_no_recent_notes(self, tmp_settings):
        chroma = MagicMock()
        chroma.get_recently_modified.side_effect = [[], [{"title": "Note A"}]]
        chroma.search.return_value = [{"text": "Résumé de la note A"}]
        rag = MagicMock()
        rag._llm.chat.return_value = "Synthèse hebdomadaire."
        learner = AutoLearner(chroma, rag, MagicMock())
        now = datetime.fromisoformat("2026-04-11T12:00:00+00:00")

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.autolearn._utc_now", return_value=now),
            patch("src.learning.autolearn._utc_now_naive", return_value=now.replace(tzinfo=None)),
        ):
            learner._weekly_synthesis()
            learner._weekly_synthesis()

        created = list(tmp_settings.synthesis_dir.glob("semaine_*.md"))
        assert len(created) == 1
        content = created[0].read_text(encoding="utf-8")
        assert "# Synthèse de la semaine" in content
        assert "Synthèse hebdomadaire." in content

    def test_record_processing_time_trims_history_and_ignores_replace_error(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        times_file = tmp_settings.processing_times_file
        times_file.parent.mkdir(parents=True, exist_ok=True)
        times_file.write_text(json.dumps([float(i) for i in range(100)]), encoding="utf-8")

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner._record_processing_time(123.456)

        saved = json.loads(times_file.read_text(encoding="utf-8"))
        assert len(saved) == 100
        assert saved[-1] == 123.5

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.autolearn.os.replace", side_effect=OSError("replace failed")),
        ):
            learner._record_processing_time(5.0)

    def test_mark_processed_updates_processed_map(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_load_processed", return_value={"old.md": "2026-04-01T10:00:00"}),
            patch.object(learner, "_save_processed") as save_processed,
            patch("src.learning.autolearn._utc_now_naive", return_value=datetime(2026, 4, 11, 12, 0, 0)),
        ):
            learner._mark_processed("note.md")

        save_processed.assert_called_once_with({
            "old.md": "2026-04-01T10:00:00",
            "note.md": "2026-04-11T12:00:00",
        })

    def test_process_and_mark_note_records_timing_and_returns_true(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        note_meta = {"file_path": "note.md", "title": "Note"}

        with (
            patch.object(learner, "_process_note") as process_note,
            patch.object(learner, "_mark_processed") as mark_processed,
            patch.object(learner, "_record_processing_time") as record_processing_time,
            patch("src.learning.autolearn.time.sleep") as sleep,
            patch("src.learning.autolearn.time.perf_counter", side_effect=[10.0, 14.2]),
        ):
            result = learner._process_and_mark_note(
                note_meta,
                sleep_between_questions=0,
                sleep_after_note=2,
                error_prefix="bulk",
            )

        assert result is True
        process_note.assert_called_once_with(note_meta, sleep_between_questions=0)
        mark_processed.assert_called_once_with("note.md")
        sleep.assert_called_once_with(2)
        assert record_processing_time.call_args[0][0] == pytest.approx(4.2)

    def test_process_and_mark_note_logs_warning_and_returns_false_on_failure(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        note_meta = {"file_path": "note.md", "title": "Note"}

        with (
            patch.object(learner, "_process_note", side_effect=RuntimeError("boom")),
            patch("src.learning.autolearn.logger.warning") as warning,
        ):
            result = learner._process_and_mark_note(note_meta, error_prefix="bulk")

        assert result is False
        warning.assert_called_once()

    def test_is_first_insight_run_handles_flag_threshold_and_failure(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch("src.learning.autolearn.settings", tmp_settings):
            tmp_settings.bulk_done_flag_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_settings.bulk_done_flag_file.write_text("done", encoding="utf-8")
            assert learner._is_first_insight_run() is False
            tmp_settings.bulk_done_flag_file.unlink()

        learner._chroma.list_notes.return_value = [{"file_path": f"note_{i}.md"} for i in range(12)]
        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_load_processed", return_value={"note_0.md": "x"}),
        ):
            assert learner._is_first_insight_run() is True

        learner._chroma.list_notes.side_effect = RuntimeError("boom")
        with patch("src.learning.autolearn.settings", tmp_settings):
            assert learner._is_first_insight_run() is False

    def test_wait_for_idle_and_log_user_query_persist_activity(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch.object(learner, "_user_is_active", side_effect=[True, True, False]):
            with patch("src.learning.autolearn.time.sleep") as sleep:
                learner._wait_for_idle("bulk")

        sleep.assert_called_once_with(10)

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch("src.learning.autolearn._utc_now_naive", return_value=datetime(2026, 4, 11, 12, 0, 0)),
        ):
            learner.log_user_query("ma requête")

        lines = tmp_settings.queries_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["query"] == "ma requête"

    def test_set_status_keeps_last_twenty_messages_and_persists(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch.object(learner, "_persist_status") as persist:
            for i in range(25):
                learner._set_status(note="note", step=f"step {i}")
            learner._clear_status()

        assert len(learner.processing_status["log"]) == 20
        assert learner.processing_status["active"] is False
        assert learner.processing_status["note"] == ""
        assert learner.processing_status["step"] == ""
        assert persist.call_count == 26

    def test_set_status_includes_file_path_in_log_entry(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch.object(learner, "_persist_status"):
            learner._set_status(note="Titre lisible", step="Récupération des chunks…", file_path="Dossiers/note-source.md")

        assert "Dossiers/note-source.md" in learner.processing_status["log"][-1]
        assert "Récupération des chunks…" in learner.processing_status["log"][-1]

    def test_run_bulk_initial_processes_pending_notes_and_sets_done_flag(self, tmp_settings):
        chroma = MagicMock()
        chroma.list_notes.return_value = [
            {"file_path": "note_1.md", "title": "Note 1"},
            {"file_path": "obsirag/insights/generated.md", "title": "Generated"},
            {"file_path": "note_2.md", "title": "Note 2"},
        ]
        chroma.search.side_effect = [RuntimeError("warming"), []]
        rag = MagicMock()
        learner = AutoLearner(chroma, rag, MagicMock(), ui_active_fn=lambda: False)
        tmp_settings.autolearn_bulk_max_notes = 1

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_load_processed", return_value={}),
            patch.object(learner, "_process_note") as process_note,
            patch.object(learner, "_mark_processed") as mark_processed,
            patch.object(learner, "_record_processing_time"),
            patch.object(learner, "_set_status"),
            patch.object(learner, "_clear_status") as clear_status,
            patch("src.learning.autolearn.time.sleep"),
        ):
            learner._run_bulk_initial()

        rag._llm.load.assert_called_once()
        process_note.assert_called_once()
        mark_processed.assert_called_once_with("note_1.md")
        rag._llm.unload.assert_called_once()
        assert tmp_settings.bulk_done_flag_file.exists()
        assert learner._bulk_initial_done.is_set() is True
        assert learner.processing_status["bulk_pending_total"] == 0
        assert learner.processing_status["bulk_new_done"] == 0
        clear_status.assert_called_once()

    def test_run_bulk_initial_handles_model_load_failure(self, tmp_settings):
        rag = MagicMock()
        rag._llm.load.side_effect = RuntimeError("mlx unavailable")
        learner = AutoLearner(MagicMock(), rag, MagicMock())

        with patch("src.learning.autolearn.settings", tmp_settings):
            learner._run_bulk_initial()

        assert learner._bulk_initial_done.is_set() is True

    def test_process_note_skips_when_no_chunks_even_if_metric_fails(self):
        chroma = MagicMock()
        chroma.search.return_value = []
        learner = AutoLearner(chroma, MagicMock(), MagicMock())
        learner._metrics = MagicMock()
        learner._metrics.increment.side_effect = RuntimeError("metrics down")

        with patch.object(learner, "_set_status"):
            learner._process_note({"file_path": "note.md", "title": "Note"}, sleep_between_questions=0)

    def test_process_note_updates_relative_path_after_obsirag_rename(self, tmp_settings):
        chroma = MagicMock()
        chroma.search.return_value = [{"text": "Extrait utile"}]
        rag = MagicMock()
        rag.query.return_value = (
            "Réponse suffisamment longue pour être conservée.",
            [{"metadata": {"file_path": "source.md"}}],
        )
        learner = AutoLearner(chroma, rag, MagicMock())
        note_meta = {"file_path": "obsirag/insights/original.md", "title": "Original", "tags": []}
        original_abs = tmp_settings.vault / "obsirag/insights/original.md"
        original_abs.parent.mkdir(parents=True, exist_ok=True)
        original_abs.write_text("Contenu", encoding="utf-8")
        renamed_abs = tmp_settings.vault / "obsirag/insights/Nouveau titre.md"

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_generate_questions", return_value=["Quelle question ?"]),
            patch.object(learner, "_web_search", return_value=[]),
            patch.object(learner, "_is_weak_answer", return_value=False),
            patch.object(learner, "_save_knowledge_artifact"),
            patch.object(learner, "_suggest_note_title", return_value="Nouveau titre"),
            patch.object(learner, "_rename_note_in_vault", return_value=renamed_abs) as rename_note,
            patch.object(learner, "_set_status"),
        ):
            learner._process_note(note_meta, sleep_between_questions=0)

        rename_note.assert_called_once_with(original_abs, "Nouveau titre", "obsirag/insights/original.md")
        assert note_meta["file_path"] == "obsirag/insights/Nouveau titre.md"

    def test_start_first_run_creates_threads_and_stop_shuts_scheduler(self, tmp_settings):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        learner._scheduler = MagicMock()
        learner._scheduler.running = True
        created_threads: list[_FakeThread] = []

        def _thread_factory(*, target=None, daemon=None, name=None):
            thread = _FakeThread(target=target, daemon=daemon, name=name)
            created_threads.append(thread)
            return thread

        with (
            patch("src.learning.autolearn.settings", tmp_settings),
            patch.object(learner, "_is_first_insight_run", return_value=True),
            patch("src.learning.autolearn.threading.Thread", side_effect=_thread_factory),
        ):
            learner.start()
            learner.stop()

        assert [t.name for t in created_threads] == ["autolearn-bulk-initial", "autolearn-scheduler-init"]
        assert all(t.started for t in created_threads)
        learner._scheduler.shutdown.assert_called_once_with(wait=False)

    def test_fetch_url_content_handles_pdf_html_cleanup_and_low_quality_text(self):
        html = "<html><head><style>x</style><script>y</script></head><body>bonjourMonde test propre</body></html>"

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(html, headers={"Content-Type": "text/html"})):
            text = AutoLearner._fetch_url_content("https://example.com/page")

        assert "bonjour Monde" in text
        assert "<script" not in text

        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse("pdf", headers={"Content-Type": "application/pdf"})):
            assert AutoLearner._fetch_url_content("https://example.com/doc") == ""

        long_words = " ".join(["x" * 20] * 20)
        with patch("urllib.request.urlopen", return_value=_FakeUrlResponse(long_words, headers={"Content-Type": "text/plain"})):
            assert AutoLearner._fetch_url_content("https://example.com/bad") == ""

        assert AutoLearner._fetch_url_content("https://example.com/file.pdf") == ""

    def test_synthesize_web_sources_deduplicates_refs_and_handles_failures(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        qa_pairs = [
            {"web_refs": [{"url": "https://a", "title": "A"}, {"url": "https://a", "title": "A"}]},
            {"web_refs": [{"url": "https://b", "title": "B"}]},
        ]

        with (
            patch.object(learner, "_fetch_url_content", side_effect=["contenu A", "contenu B"]),
            patch.object(learner, "_fit_context", return_value=("", "CTX")),
        ):
            learner._rag._llm.chat.return_value = "Synthèse web"
            assert learner._synthesize_web_sources("Note", qa_pairs) == "Synthèse web"

        with patch.object(learner, "_fetch_url_content", return_value=""):
            assert learner._synthesize_web_sources("Note", qa_pairs) == ""

        learner._rag._llm.chat.side_effect = RuntimeError("boom")
        with (
            patch.object(learner, "_fetch_url_content", return_value="contenu A"),
            patch.object(learner, "_fit_context", return_value=("", "CTX")),
        ):
            assert learner._synthesize_web_sources("Note", qa_pairs) == ""

    def test_web_search_prefers_trusted_results_and_falls_back_on_error(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, max_results=15):
                return [
                    {"href": "https://example.com", "body": "ignored", "title": "x"},
                    {"href": "https://wikipedia.org/wiki/Test", "body": "trusted", "title": "y"},
                    {"href": "https://reuters.com/test", "body": "trusted2", "title": "z"},
                ]

        with patch.dict(sys.modules, {"ddgs": SimpleNamespace(DDGS=_FakeDDGS)}):
            results = learner._web_search("question")

        assert [r["body"] for r in results] == ["trusted", "trusted2"]

        with patch.dict(sys.modules, {"ddgs": SimpleNamespace(DDGS=lambda: (_ for _ in ()).throw(RuntimeError("boom")))}):
            assert learner._web_search("question") == []

    def test_enrich_with_web_returns_original_when_irrelevant_or_llm_fails(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())

        with patch.object(learner, "_snippets_relevant", return_value=False):
            assert learner._enrich_with_web("question", "base", ["snippet"]) == "base"

        learner._rag._llm.chat.side_effect = RuntimeError("boom")
        with (
            patch.object(learner, "_snippets_relevant", return_value=True),
            patch.object(learner, "_fit_context", return_value=("", "CTX")),
        ):
            assert learner._enrich_with_web("question", "base", ["snippet"]) == "base"

        learner._rag._llm.chat.side_effect = None
        learner._rag._llm.chat.return_value = "enrichie"
        with (
            patch.object(learner, "_snippets_relevant", return_value=True),
            patch.object(learner, "_fit_context", return_value=("", "CTX")),
        ):
            assert learner._enrich_with_web("question", "base", ["snippet"]) == "enrichie"

    def test_generate_questions_extracts_clean_question_and_handles_failure(self):
        learner = AutoLearner(MagicMock(), MagicMock(), MagicMock())
        learner._rag._llm.chat.return_value = "1. Quelle est l'évolution récente du sujet ?\nRéponse"

        questions = learner._generate_questions("contenu", already_asked=["ancienne question ?"])

        assert questions == ["Quelle est l'évolution récente du sujet ?"]
        sent_prompt = learner._rag._llm.chat.call_args[0][0][0]["content"]
        assert "<deja_posees>" in sent_prompt

        learner._rag._llm.chat.side_effect = RuntimeError("boom")
        assert learner._generate_questions("contenu") == []
