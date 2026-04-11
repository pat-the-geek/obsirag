from __future__ import annotations

import pytest

from src.ui.note_badges import (
    get_note_graph_color,
    get_note_type,
    get_note_type_options,
    prefix_note_label,
    render_note_badge,
)


@pytest.mark.unit
class TestNoteBadges:
    def test_get_note_type_distinguishes_user_insight_synapse_and_report(self):
        assert get_note_type("notes/idea.md") == "user"
        assert get_note_type("obsirag/insights/alpha.md") == "insight"
        assert get_note_type("vault/obsirag/synapses/link.md") == "synapse"
        assert get_note_type("obsirag/synthesis/week-15.md") == "report"

    def test_prefix_note_label_includes_icon_and_label(self):
        label = prefix_note_label("Weekly Review", "obsirag/synthesis/week-15.md")

        assert label.startswith("📋 Rapport · ")
        assert "Weekly Review" in label

    def test_render_note_badge_contains_human_label(self):
        html = render_note_badge("obsirag/insights/alpha.md")

        assert "Insight" in html
        assert "💡" in html

    def test_get_note_type_options_returns_expected_order(self):
        options = get_note_type_options()

        assert [option["key"] for option in options] == ["user", "report", "insight", "synapse"]
        assert options[1]["label"] == "Rapport"

    def test_get_note_graph_color_uses_type_palette(self):
        color = get_note_graph_color("obsirag/synthesis/week-15.md")

        assert color["background"] == "#f59e0b"
        assert color["border"] == "#b45309"
        assert color["highlight"]["background"] == "#fcd34d"