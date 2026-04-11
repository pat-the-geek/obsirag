"""
Tests unitaires — Configuration (src/config.py)
"""
import pytest
from pathlib import Path
from src.config import Settings


@pytest.mark.unit
class TestSettings:
    def test_default_vault_path(self):
        s = Settings(vault_path="/vault", app_data_dir="/app/data")
        assert s.vault == Path("/vault")

    def test_derived_chroma_dir(self, tmp_settings):
        assert tmp_settings.chroma_persist_dir.endswith("/chroma")

    def test_derived_index_state_file(self, tmp_settings):
        assert tmp_settings.index_state_file.name == "index_state.json"

    def test_derived_token_stats_file(self, tmp_settings):
        assert tmp_settings.token_stats_file.name == "token_usage.json"

    def test_insights_dir_inside_vault(self, tmp_settings):
        assert str(tmp_settings.insights_dir).startswith(str(tmp_settings.vault))

    def test_synthesis_dir_inside_vault(self, tmp_settings):
        assert str(tmp_settings.synthesis_dir).startswith(str(tmp_settings.vault))

    def test_obsidian_vault_name_fallback(self, tmp_settings):
        # Pas de nom explicite → utilise le nom du dossier
        assert tmp_settings.obsidian_vault == Path(tmp_settings.vault_path).name

    def test_obsidian_vault_name_explicit(self, tmp_path):
        s = Settings(
            vault_path=str(tmp_path / "mon-coffre"),
            app_data_dir=str(tmp_path / "data"),
            obsidian_vault_name="MonCoffre",
        )
        assert s.obsidian_vault == "MonCoffre"

    def test_data_dir(self, tmp_settings):
        assert tmp_settings.data_dir == Path(tmp_settings.app_data_dir)

    def test_graph_dir_inside_data(self, tmp_settings):
        assert str(tmp_settings.graph_dir).startswith(str(tmp_settings.data_dir))

    def test_processing_status_file(self, tmp_settings):
        assert tmp_settings.processing_status_file.name == "processing_status.json"

    def test_processing_times_file(self, tmp_settings):
        assert tmp_settings.processing_times_file.name == "processing_times.json"

    def test_queries_file(self, tmp_settings):
        assert tmp_settings.queries_file.name == "queries.jsonl"

    def test_processed_notes_file(self, tmp_settings):
        assert tmp_settings.processed_notes_file.name == "processed_notes.json"

    def test_bulk_done_flag_file(self, tmp_settings):
        assert tmp_settings.bulk_done_flag_file.name == "bulk_done.flag"

    def test_synapses_dir_inside_vault(self, tmp_settings):
        assert str(tmp_settings.synapses_dir).startswith(str(tmp_settings.vault))

    def test_conversations_dir_inside_vault(self, tmp_settings):
        assert str(tmp_settings.conversations_dir).startswith(str(tmp_settings.vault))

    def test_synapse_index_file(self, tmp_settings):
        assert tmp_settings.synapse_index_file.name == "synapse_index.json"

    def test_knowledge_dir_aliases_insights_dir(self, tmp_settings):
        assert tmp_settings.knowledge_dir == tmp_settings.insights_dir

    def test_autolearn_defaults(self):
        s = Settings(vault_path="/v", app_data_dir="/d")
        assert s.autolearn_interval_minutes > 0
        assert s.autolearn_max_notes_per_run > 0
        assert 0 <= s.autolearn_active_hour_start < s.autolearn_active_hour_end <= 24

    def test_chunk_size_positive(self):
        s = Settings(vault_path="/v", app_data_dir="/d")
        assert s.chunk_size_words > 0
        assert s.chunk_overlap_words >= 0
        assert s.chunk_overlap_words < s.chunk_size_words
