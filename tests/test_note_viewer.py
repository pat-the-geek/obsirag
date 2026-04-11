from __future__ import annotations

import pytest

from src.ui.note_viewer import (
    count_mermaid_blocks,
    extract_note_outline,
    find_note_matches,
    inject_line_anchors,
    make_note_anchor,
    strip_frontmatter,
)


@pytest.mark.unit
class TestNoteViewerHelpers:
    def test_strip_frontmatter_removes_yaml_header(self):
        content = "---\ntitle: Demo\n---\n\n# Heading\nBody"
        assert strip_frontmatter(content).lstrip().startswith("# Heading")

    def test_extract_note_outline_returns_heading_levels_and_lines(self):
        content = "---\ntitle: Demo\n---\nIntro\n# Alpha\nTexte\n## Beta\nSuite"

        outline = extract_note_outline(content)

        assert outline == [
            {"level": 1, "title": "Alpha", "line": 2},
            {"level": 2, "title": "Beta", "line": 4},
        ]

    def test_count_mermaid_blocks_counts_fenced_diagrams(self):
        content = "```mermaid\ngraph TD\nA-->B\n```\n\n```mermaid\nflowchart LR\nX-->Y\n```"
        assert count_mermaid_blocks(content) == 2

    def test_inject_line_anchors_adds_anchor_outside_code_fences(self):
        content = "# Alpha\nTexte\n```python\nprint('x')\n```\n## Beta"

        rendered = inject_line_anchors(content, {1, 4, 6})

        assert f'<span id="{make_note_anchor(1)}"></span>' in rendered
        assert f'<span id="{make_note_anchor(6)}"></span>' in rendered
        assert f'<span id="{make_note_anchor(4)}"></span>' not in rendered

    def test_find_note_matches_returns_heading_and_content_matches(self):
        content = "# Alpha Section\nTexte banal\n## Beta\nPython est utile pour la data science."

        matches = find_note_matches(content, "python")

        assert matches == [
            {"section": "Beta", "snippet": "Python est utile pour la data science.", "line": 4}
        ]

    def test_find_note_matches_limits_results_and_matches_headings(self):
        content = "# Python\nTexte\n## Python avancé\nSuite\n### Python expert\nFin"

        matches = find_note_matches(content, "python", max_results=2)

        assert len(matches) == 2
        assert matches[0]["section"] == "Python"
        assert matches[1]["section"] == "Python avancé"