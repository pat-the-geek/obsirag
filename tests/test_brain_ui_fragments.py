from __future__ import annotations

import pytest

from src.ui.brain_ui_fragments import (
    build_badge_row_html,
    build_brain_note_row_html,
    build_brain_page_header_html,
)


@pytest.mark.unit
class TestBrainUiFragments:
    def test_build_brain_page_header_html_embeds_svg_base64(self):
        html = build_brain_page_header_html("XYZ")

        assert "data:image/svg+xml;base64,XYZ" in html
        assert "Cerveau" in html

    def test_build_badge_row_html_keeps_badges_order(self):
        html = build_badge_row_html(["<span>a</span>", "<span>b</span>"])

        assert "<span>a</span><span>b</span>" in html

    def test_build_brain_note_row_html_escapes_title_and_subtitle(self):
        html = build_brain_note_row_html("<span>badge</span>", "Titre <A>", "sous <B>")

        assert "Titre &lt;A&gt;" in html
        assert "sous &lt;B&gt;" in html
        assert "<span>badge</span>" in html