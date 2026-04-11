from __future__ import annotations

import pytest

from src.ui.chat_mermaid import (
    build_mermaid_chat_preview_html,
    build_mermaid_fullscreen_html,
    estimate_chat_mermaid_height,
)


@pytest.mark.unit
class TestChatMermaid:
    def test_build_mermaid_fullscreen_html_includes_zoom_runtime(self):
        html = build_mermaid_fullscreen_html("graph TD\nA-->B", 3)

        assert "svg-pan-zoom.min.js" in html
        assert "mermaid.render('diag_3',CODE)" in html
        assert "ObsiRAG" in html
        assert "Rendu en cours" in html

    def test_build_mermaid_chat_preview_html_includes_fullscreen_payload(self):
        html = build_mermaid_chat_preview_html("graph TD\nA-->B", 5)

        assert "Cliquer pour plein écran" in html
        assert "window.open('','_blank')" in html
        assert "mermaid.render('prev_5',CODE)" in html
        assert "FS_B64" in html

    def test_estimate_chat_mermaid_height_clamps_bounds(self):
        assert estimate_chat_mermaid_height("graph TD\nA-->B") == 220
        assert estimate_chat_mermaid_height("\n".join(["A-->B"] * 50)) == 600