from __future__ import annotations

import pytest

from src.ui.note_ui_fragments import (
    build_obsidian_open_link_html,
    build_outline_item_html,
    build_search_match_html,
)


@pytest.mark.unit
class TestNoteUiFragments:
    def test_build_obsidian_open_link_html_escapes_url(self):
        html = build_obsidian_open_link_html('obsidian://open?vault=A&B="x"')

        assert "obsidian://open?vault=A&amp;B=&quot;x&quot;" in html
        assert "Ouvrir dans Obsidian" in html

    def test_build_outline_item_html_includes_indent_title_and_line(self):
        html = build_outline_item_html("Titre <A>", line=12, level=3)

        assert "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;" in html
        assert "Titre &lt;A&gt;" in html
        assert "(ligne 12)" in html

    def test_build_search_match_html_escapes_section_and_snippet(self):
        html = build_search_match_html("Section <B>", line=8, snippet="x < y")

        assert "Section &lt;B&gt;" in html
        assert "ligne 8" in html
        assert "x &lt; y" in html