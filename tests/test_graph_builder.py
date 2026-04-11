from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from src.graph.builder import GraphBuilder, _tmp_workdir


@pytest.mark.unit
class TestGraphBuilder:
    def test_tmp_workdir_restores_original_directory(self, tmp_path):
        original = Path.cwd()
        target = tmp_path / "cwd"
        target.mkdir()

        with _tmp_workdir(str(target)):
            assert Path.cwd() == target

        assert Path.cwd() == original

    def test_build_creates_nodes_edges_and_timezone_aware_timestamp(self, tmp_settings):
        notes = [
            {
                "file_path": "folder/A.md",
                "title": "Alpha",
                "date_modified": "2026-04-10T10:00:00",
                "tags": ["python"],
                "wikilinks": ["Beta"],
            },
            {
                "file_path": "folder/B.md",
                "title": "Beta",
                "date_modified": "2026-04-11T11:00:00",
                "tags": [],
                "wikilinks": [],
            },
        ]
        builder = GraphBuilder()

        with patch("src.graph.builder.settings", tmp_settings):
            graph = builder.build(notes)

        assert graph.has_node("folder/A.md")
        assert graph.has_edge("folder/A.md", "folder/B.md")
        assert graph.nodes["folder/A.md"]["label"] == "Alpha"
        assert graph.nodes["folder/A.md"]["note_type"] == "user"
        assert graph.nodes["folder/A.md"]["note_type_label"] == "Note"
        assert graph.nodes["folder/A.md"]["color"]["background"] == "#60a5fa"
        assert builder._last_build is not None
        assert builder._last_build.tzinfo is not None
        assert (tmp_settings.graph_dir / "knowledge_graph.json").exists()

    def test_build_falls_back_to_stem_when_title_missing(self, tmp_settings):
        builder = GraphBuilder()
        notes = [{"file_path": "folder/No Title.md", "tags": [], "wikilinks": []}]

        with patch("src.graph.builder.settings", tmp_settings):
            graph = builder.build(notes)

        assert graph.nodes["folder/No Title.md"]["label"] == "No Title"

    def test_to_pyvis_html_injects_css_and_vault_name(self):
        builder = GraphBuilder()
        graph = nx.DiGraph()
        graph.add_node("Note.md", label="Note", title="<b>Note</b>", color="#fff", size=12)

        fake_net = MagicMock()

        def _write_html(path, local=False):
            Path(path).write_text("<html><head></head><body><script>var network = {};</script></body></html>", encoding="utf-8")

        fake_net.write_html.side_effect = _write_html

        with (
            patch("src.graph.builder.Network", return_value=fake_net),
            patch("src.graph.builder._tmp_workdir") as tmp_workdir,
        ):
            tmp_workdir.return_value.__enter__.return_value = None
            tmp_workdir.return_value.__exit__.return_value = None
            html = builder.to_pyvis_html(graph, obsidian_vault="Vault Test")

        assert "obsirag-tooltip" in html
        assert "Vault Test" in html
        assert "waitForNetwork" in html
        assert "obsirag-open-note" in html
        assert "obsirag-open-obsidian" in html
        assert "document.createElement('iframe')" in html
        assert "localStorage.setItem('obsirag_open_note', fp)" in html
        assert "window.parent.postMessage({ obsirag_open_note: fp }, '*')" in html
        fake_net.add_node.assert_called_once()

    def test_to_pyvis_html_colors_semantic_edges_in_green(self):
        builder = GraphBuilder()
        graph = nx.DiGraph()
        graph.add_node("A.md", label="A", title="A")
        graph.add_node("B.md", label="B", title="B")
        graph.add_edge("A.md", "B.md", edge_type="semantic")

        fake_net = MagicMock()

        def _write_html(path, local=False):
            Path(path).write_text("<html><head></head><body><script>var network = {};</script></body></html>", encoding="utf-8")

        fake_net.write_html.side_effect = _write_html

        with (
            patch("src.graph.builder.Network", return_value=fake_net),
            patch("src.graph.builder._tmp_workdir") as tmp_workdir,
        ):
            tmp_workdir.return_value.__enter__.return_value = None
            tmp_workdir.return_value.__exit__.return_value = None
            builder.to_pyvis_html(graph)

        fake_net.add_edge.assert_called_once_with("A.md", "B.md", color="#059669")

    def test_get_stats_returns_top_connected_and_density(self):
        graph = nx.DiGraph()
        graph.add_edge("A.md", "B.md")
        graph.add_edge("B.md", "C.md")

        stats = GraphBuilder().get_stats(graph)

        assert stats["nodes"] == 3
        assert stats["edges"] == 2
        assert stats["top_connected"][0]["file_path"] == "B.md"
        assert stats["density"] > 0

    def test_get_stats_returns_empty_for_empty_graph(self):
        assert GraphBuilder().get_stats(nx.DiGraph()) == {}

    def test_node_tooltip_escapes_title_and_file_path(self):
        tooltip = GraphBuilder._node_tooltip(
            {
                "title": "A < B",
                "file_path": 'folder/a"b.md',
                "date_modified": "2026-04-11T11:00:00",
                "tags": ["x", "y"],
            }
        )

        assert "A &lt; B" in tooltip
        assert "a&quot;b.md" in tooltip
        assert "📝 Note" in tooltip

    def test_resolve_link_is_case_insensitive(self):
        assert GraphBuilder._resolve_link("alpha", {"alpha": "Alpha.md"}) == "Alpha.md"
        assert GraphBuilder._resolve_link("missing", {"alpha": "Alpha.md"}) is None

    def test_save_json_logs_warning_on_write_failure(self, tmp_settings):
        graph = nx.DiGraph()
        graph.add_node("A.md")
        builder = GraphBuilder()

        with (
            patch("src.graph.builder.settings", tmp_settings),
            patch("pathlib.Path.write_text", side_effect=OSError("readonly")),
            patch("src.graph.builder.logger.warning") as warning,
        ):
            builder._save_json(graph)

        warning.assert_called_once()

    def test_save_json_writes_node_link_data(self, tmp_settings):
        graph = nx.DiGraph()
        graph.add_edge("A.md", "B.md")
        builder = GraphBuilder()

        with patch("src.graph.builder.settings", tmp_settings):
            builder._save_json(graph)

        saved = json.loads((tmp_settings.graph_dir / "knowledge_graph.json").read_text(encoding="utf-8"))
        assert len(saved["nodes"]) == 2
        assert len(saved.get("links", saved.get("edges", []))) == 1