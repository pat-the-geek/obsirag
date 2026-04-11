from __future__ import annotations

import pytest

from src.ui.mermaid_embed import build_mermaid_html_document, estimate_mermaid_height


@pytest.mark.unit
class TestMermaidEmbed:
    def test_build_mermaid_html_document_includes_runtime_and_code(self):
        html = build_mermaid_html_document("graph TD\nA-->B", 7)

        assert "mermaid.min.js" in html
        assert "mermaid.render('mg7', code)" in html
        assert "const code = \"graph TD\\nA-->B\";" in html
        assert "⚠ Erreur Mermaid" in html

    def test_estimate_mermaid_height_clamps_bounds(self):
        assert estimate_mermaid_height("graph TD\nA-->B") == 200
        assert estimate_mermaid_height("\n".join(["A-->B"] * 50)) == 600