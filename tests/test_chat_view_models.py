from __future__ import annotations

import pytest

from src.ui.chat_view_models import (
    build_generation_summary_caption,
    build_navigation_meta,
    build_navigation_turn_title,
    build_saved_conversation_meta,
    build_saved_conversation_title,
    build_web_sources_markdown,
)


@pytest.mark.unit
class TestChatViewModels:
    def test_build_navigation_helpers(self):
        assert build_navigation_turn_title(3, "Question") == "**Tour 3** · Question"
        assert build_navigation_meta(2, "Note A") == "2 source(s) · source: Note A"
        assert build_navigation_meta(None, None) == ""

    def test_build_saved_conversation_helpers(self):
        assert build_saved_conversation_title("Demo") == "**Demo**"
        assert build_saved_conversation_meta("2026-04", "obsirag/conversations/a.md") == "2026-04 · obsirag/conversations/a.md"

    def test_build_generation_summary_caption(self):
        assert build_generation_summary_caption(1.24, 8.67) == "TTFT 1.2s · total 8.7s"

    def test_build_web_sources_markdown(self):
        md = build_web_sources_markdown([
            {"title": "Doc A", "href": "https://a"},
            {"href": "https://b"},
        ])

        assert "- [Doc A](https://a)" in md
        assert "- [https://b](https://b)" in md