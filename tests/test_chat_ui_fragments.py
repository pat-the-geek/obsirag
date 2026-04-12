from __future__ import annotations

import pytest

from src.ui.chat_ui_fragments import (
    build_cited_source_row_html,
    build_generation_status_caption,
    build_message_stats_caption,
    build_primary_source_html,
    build_sidebar_header_html,
    build_source_entry_html,
    build_user_bubble_html,
)


@pytest.mark.unit
class TestChatUiFragments:
    def test_primary_source_html_includes_badge_and_escaped_title(self):
        html = build_primary_source_html("Note <Alpha>", "<span>badge</span>")

        assert "Note principale" in html
        assert "<span>badge</span>" in html
        assert "Note &lt;Alpha&gt;" in html

    def test_source_entry_html_formats_score_date_and_primary_flag(self):
        html = build_source_entry_html(
            note_title="Ma source",
            note_badge_html="<span>badge</span>",
            date_modified="2026-04-12T10:15:00",
            score=0.987,
            is_primary=True,
        )

        assert "Principale" in html
        assert "2026-04-12" in html
        assert "Score 0.99" in html
        assert "<strong>Ma source</strong>" in html

    @pytest.mark.nrt
    def test_user_bubble_html_escapes_user_content(self):
        html = build_user_bubble_html("<script>alert(1)</script>", "<svg></svg>")

        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<svg></svg>" in html

    @pytest.mark.nrt
    def test_sidebar_header_html_embeds_base64_icon(self):
        html = build_sidebar_header_html("ABC123")

        assert "data:image/png;base64,ABC123" in html
        assert "ObsiRAG" in html

    def test_generation_status_caption_is_stable_for_snapshot_like_checks(self):
        caption = build_generation_status_caption(128, 1.25, 5.4, 29.7)

        assert caption == "✅ 128 tokens · TTFT 1.2s · 5.4s total · 30 tok/s"

    def test_cited_source_row_html_escapes_title_and_keeps_badge(self):
        html = build_cited_source_row_html("Titre <A>", "<span>badge</span>")

        assert "Titre &lt;A&gt;" in html
        assert "<span>badge</span>" in html

    def test_message_stats_caption_uses_lightning_bolt_and_formats_values(self):
        caption = build_message_stats_caption(200, 0.8, 3.7, 54.0)

        assert caption.startswith("⚡")
        assert "200 tokens" in caption
        assert "TTFT 0.8s" in caption
        assert "3.7s total" in caption
        assert "54 tok/s" in caption