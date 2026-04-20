from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.ai.answer_prompting import AnswerPrompting
from src.learning.artifact_writer import AutoLearnArtifactWriter
from src.learning.synapse_discovery import AutoLearnSynapseDiscovery
from src.learning.web_enrichment import AutoLearnWebEnrichment
from src.metrics import MetricsRecorder
from src.storage.slugify import build_ascii_stem


def _chunk(
    text: str,
    *,
    file_path: str = "note.md",
    note_title: str = "Note",
    wikilinks: str = "",
    section_title: str = "",
) -> dict:
    return {
        "chunk_id": f"{file_path}-0",
        "text": text,
        "metadata": {
            "file_path": file_path,
            "note_title": note_title,
            "date_modified": "2026-04-02T10:00:00",
            "wikilinks": wikilinks,
            "section_title": section_title,
        },
        "score": 0.9,
    }


@pytest.mark.unit
class TestMetricsRecorder:
    def test_increment_and_observe_persist_counters_and_summary(self, tmp_path):
        metrics_file = tmp_path / "metrics.json"
        recorder = MetricsRecorder(lambda: metrics_file)

        recorder.increment("rag_queries_total")
        recorder.increment("rag_queries_total", amount=2)
        recorder.observe("autolearn_cycle_seconds", 1.5)
        recorder.observe("autolearn_cycle_seconds", 2.5)

        payload = json.loads(metrics_file.read_text(encoding="utf-8"))
        assert payload["counters"]["rag_queries_total"] == 3
        assert payload["summaries"]["autolearn_cycle_seconds"] == {
            "count": 2,
            "total": 4.0,
            "avg": 2.0,
            "last": 2.5,
        }


@pytest.mark.unit
class TestAnswerPromptingHelpers:
    def test_load_linked_chunks_uses_file_path_lookup_for_resolved_target(self):
        owner = MagicMock()
        prompting = AnswerPrompting(owner)
        owner._get_linked_chunks_by_file_path.return_value = [_chunk("Contenu lié", file_path="linked.md")]

        chunks = prompting.load_linked_chunks("linked.md")

        owner._get_linked_chunks_by_file_path.assert_called_once_with("linked.md", limit=2)
        assert chunks[0]["metadata"]["file_path"] == "linked.md"

    def test_collect_linked_targets_adds_resolved_and_unresolved_targets(self):
        owner = MagicMock()
        prompting = AnswerPrompting(owner)
        seen_notes = {"a.md": [_chunk("Contenu A", file_path="a.md", note_title="Note A", wikilinks="Note B, Note C")]}

        with patch.object(prompting, "build_title_to_file_index", return_value={"note b": "b.md"}):
            linked_targets = prompting.collect_linked_targets(seen_notes)

        assert linked_targets == {"b.md", "__title__:Note C"}

    def test_render_context_from_seen_notes_honors_budget_and_truncates_lines(self):
        owner = MagicMock()
        owner._get_settings.return_value = SimpleNamespace(max_context_chars=120, max_chunk_chars=20)
        prompting = AnswerPrompting(owner)

        context = prompting.render_context_from_seen_notes(
            {
                "a.md": [_chunk("A" * 40, file_path="a.md", note_title="Note A", section_title="Section")],
                "b.md": [_chunk("B" * 40, file_path="b.md", note_title="Note B")],
            },
            char_budget=45,
        )

        assert "### [Note A]" in context
        assert "…" in context
        assert "Note B" not in context


@pytest.mark.unit
class TestArtifactWriterHelpers:
    def test_build_ascii_stem_replaces_non_latin_sequences_with_ascii_safe_separators(self):
        assert build_ascii_stem(
            "Lopen_source_est_mort___ce_projet_majeur__Meta暂停与Mercor合作因数据泄露",
            fallback="artifact",
            max_length=80,
            separator="_",
        ) == "Lopen_source_est_mort_ce_projet_majeur_Meta_Mercor"

    def test_filter_source_paths_prefers_user_sources_over_obsirag_artifacts(self):
        assert AutoLearnArtifactWriter.filter_source_paths([
            "obsirag/synapses/demo.md",
            "folder/note.md",
            "folder/note.md",
        ]) == ["folder/note.md"]

    def test_render_qa_sections_falls_back_to_source_note_when_sources_are_only_obsirag(self):
        writer = AutoLearnArtifactWriter(MagicMock())

        lines = writer.render_qa_sections(
            [{
                "question": "Q ?",
                "answer": "R",
                "sources": ["obsirag/synapses/demo.md", "obsirag/web_insights/demo.md"],
            }],
            provenance="Coffre",
            source_note_path="folder/source.md",
        )

        assert "*Notes consultées : [[folder/source]]*  " in lines

    def test_normalize_provenance_label_maps_mixed_forms(self):
        assert AutoLearnArtifactWriter.normalize_provenance_label("Web + Coffre") == "Coffre et Web"
        assert AutoLearnArtifactWriter.normalize_provenance_label("Coffre + Web") == "Coffre et Web"
        assert AutoLearnArtifactWriter.normalize_provenance_label("Web") == "Web"

    def test_compute_global_provenance_defaults_to_coffre(self):
        assert AutoLearnArtifactWriter.compute_global_provenance([
            {"provenance": "Coffre"},
            {},
        ]) == "Coffre"

    def test_compute_global_provenance_normalizes_web_plus_coffre(self):
        assert AutoLearnArtifactWriter.compute_global_provenance([
            {"provenance": "Web + Coffre"},
        ]) == "Coffre et Web"

    def test_upsert_entity_gallery_replaces_existing_section(self):
        owner = MagicMock()
        owner._build_entity_image_gallery.return_value = "![Alice](https://img/alice)"
        writer = AutoLearnArtifactWriter(owner)
        content = "## Entités clés\n\nAncienne galerie\n---\n\n## Question 1\n"

        updated = writer.upsert_entity_gallery(content, [{"type": "PERSON", "value": "Alice"}])

        assert "Ancienne galerie" not in updated
        assert "![Alice](https://img/alice)" in updated

    def test_build_new_insight_document_includes_gallery_when_available(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        owner._fetch_gpe_coordinates.return_value = None
        owner._build_entity_image_gallery.return_value = "![Paris](https://img/paris)"
        owner._synthesize_web_sources.return_value = ""
        writer = AutoLearnArtifactWriter(owner)

        content = writer.build_new_insight_document(
            "Note Test",
            {"file_path": "folder/note.md", "tags": ["source"]},
            [{"question": "Q ?", "answer": "R", "sources": ["folder/note.md"]}],
            ["source"],
            ["person/alice"],
            [{"type": "GPE", "value": "Paris"}],
            "Coffre",
        )

        assert "## Entités clés" in content
        assert "![Paris](https://img/paris)" in content

    def test_append_to_insight_records_metric_when_not_archived(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        owner._merge_frontmatter_tags.side_effect = lambda content, _tags: content
        owner._build_entity_image_gallery.return_value = ""
        owner._synthesize_web_sources.return_value = ""
        owner._metrics = MagicMock()
        writer = AutoLearnArtifactWriter(owner)

        tmp_settings.max_insight_size_bytes = 10_000
        path = tmp_settings.insights_dir / "2026-04" / "Insight.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "---\ntags:\n  - insight\n---\n# Insights\n\n**Générée le :** old\n\n## Question 1\n\n> Q\n\nA\n",
            encoding="utf-8",
        )

        writer.append_to_insight(
            path,
            [{"question": "Q2 ?", "answer": "Réponse", "sources": ["note.md"]}],
            ["person/alice"],
            "Coffre",
        )

        owner._metrics.increment.assert_called_once_with("autolearn_insights_appended_total")
        assert "## Question 2" in path.read_text(encoding="utf-8")

    def test_append_to_insight_uses_existing_note_source_as_fallback_for_obsirag_only_sources(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        owner._merge_frontmatter_tags.side_effect = lambda content, _tags: content
        owner._build_entity_image_gallery.return_value = ""
        owner._synthesize_web_sources.return_value = ""
        owner._metrics = MagicMock()
        writer = AutoLearnArtifactWriter(owner)

        tmp_settings.max_insight_size_bytes = 10_000
        path = tmp_settings.insights_dir / "2026-04" / "Insight.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Insights\n\n**Note source :** [[folder/source]]  \n**Générée le :** old\n**Provenance :** Coffre\n\n## Question 1\n\n> Q\n\nA\n",
            encoding="utf-8",
        )

        writer.append_to_insight(
            path,
            [{"question": "Q2 ?", "answer": "Réponse", "sources": ["obsirag/synapses/demo.md"]}],
            ["person/alice"],
            "Coffre",
        )

        updated = path.read_text(encoding="utf-8")
        assert "*Notes consultées : [[folder/source]]*" in updated

    def test_extract_source_note_ref_returns_wikilink_target(self):
        content = "# Insights\n\n**Note source :** [[folder/source]]  \n"

        assert AutoLearnArtifactWriter.extract_source_note_ref(content) == "folder/source"


@pytest.mark.unit
class TestWebEnrichmentHelpers:
    def test_web_search_counts_fallback_when_only_untrusted_results_exist(self):
        owner = MagicMock()
        owner._TRUSTED_DOMAINS = ["trusted.example"]
        owner._metrics = MagicMock()
        enrichment = AutoLearnWebEnrichment(owner)

        module = ModuleType("ddgs")

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, _query, max_results=15):
                assert max_results == 15
                return [
                    {"href": "https://other.example/a", "body": "snippet a", "title": "A"},
                    {"href": "https://other.example/b", "body": "snippet b", "title": "B"},
                ]

        module.DDGS = _FakeDDGS
        with (
            patch.dict("sys.modules", {"ddgs": module}),
            patch.object(AutoLearnWebEnrichment, "fetch_url_content", return_value="full content"),
        ):
            results = enrichment.web_search("question")

        owner._metrics.increment.assert_called_once_with("autolearn_web_search_fallback_total")
        assert len(results) == 2
        assert results[0]["full_text"] == "full content"

    def test_web_search_counts_error_when_provider_raises(self):
        owner = MagicMock()
        owner._TRUSTED_DOMAINS = []
        owner._metrics = MagicMock()
        enrichment = AutoLearnWebEnrichment(owner)

        module = ModuleType("ddgs")

        class _BrokenDDGS:
            def __enter__(self):
                raise RuntimeError("boom")

            def __exit__(self, exc_type, exc, tb):
                return False

        module.DDGS = _BrokenDDGS
        with patch.dict("sys.modules", {"ddgs": module}):
            assert enrichment.web_search("question") == []

        owner._metrics.increment.assert_called_once_with("autolearn_web_search_error_total")

    def test_generate_questions_returns_empty_when_llm_output_has_no_question(self):
        owner = MagicMock()
        owner._question_prompt = "Contenu: {content}{already_asked_section}"
        owner._rag._llm.chat.return_value = "- affirmation sans point d'interrogation"
        enrichment = AutoLearnWebEnrichment(owner)

        assert enrichment.generate_questions("contenu") == []


@pytest.mark.unit
class TestSynapseDiscoveryHelpers:
    def test_load_synapse_index_returns_empty_set_on_invalid_json(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        tmp_settings.synapse_index_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_settings.synapse_index_file.write_text("not json", encoding="utf-8")
        discovery = AutoLearnSynapseDiscovery(owner)

        assert discovery.load_synapse_index() == set()

    def test_discover_synapses_stops_when_quota_is_exhausted(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        owner._load_synapse_index.return_value = set()
        owner._synapse_pair_key.side_effect = AutoLearnSynapseDiscovery.synapse_pair_key
        owner._create_synapse_artifact = MagicMock()
        owner._save_synapse_index = MagicMock()
        owner._chroma.find_similar_notes.return_value = [
            {"file_path": "b.md", "title": "B", "score": 0.9, "excerpt": "B"},
            {"file_path": "c.md", "title": "C", "score": 0.8, "excerpt": "C"},
        ]
        discovery = AutoLearnSynapseDiscovery(owner)
        tmp_settings.autolearn_synapse_per_run = 1

        with patch("random.shuffle", side_effect=lambda items: None), patch("src.learning.synapse_discovery.time.sleep"):
            discovery.discover_synapses([
                {"file_path": "a.md", "title": "A", "wikilinks": []},
                {"file_path": "d.md", "title": "D", "wikilinks": []},
            ])

        owner._create_synapse_artifact.assert_called_once()

    def test_discover_synapses_logs_warning_when_artifact_creation_fails(self, tmp_settings):
        owner = MagicMock()
        owner._get_settings.return_value = tmp_settings
        owner._load_synapse_index.return_value = set()
        owner._synapse_pair_key.side_effect = AutoLearnSynapseDiscovery.synapse_pair_key
        owner._create_synapse_artifact.side_effect = RuntimeError("boom")
        owner._save_synapse_index = MagicMock()
        owner._chroma.find_similar_notes.return_value = [
            {"file_path": "b.md", "title": "B", "score": 0.9, "excerpt": "B"},
        ]
        discovery = AutoLearnSynapseDiscovery(owner)
        tmp_settings.autolearn_synapse_per_run = 1

        with (
            patch("random.shuffle", side_effect=lambda items: None),
            patch("src.learning.synapse_discovery.logger.warning") as warning,
        ):
            discovery.discover_synapses([{"file_path": "a.md", "title": "A", "wikilinks": []}])

        warning.assert_called_once()

    def test_extract_synapse_note_refs_prefers_explicit_sources(self):
        content = (
            "# Synapse\n\n"
            "**Note source A :** [[folder/a]]  \n"
            "**Note source B :** [[folder/b]]\n\n"
            "## [[Titre A]]\n\n"
            "## [[Titre B]]\n"
        )

        assert AutoLearnSynapseDiscovery.extract_synapse_note_refs(content) == ("folder/a", "folder/b")

    def test_extract_synapse_note_refs_falls_back_to_section_links(self):
        content = "## [[Titre A]]\n\nTexte\n\n## [[Titre B]]\n"

        assert AutoLearnSynapseDiscovery.extract_synapse_note_refs(content) == ("Titre A", "Titre B")