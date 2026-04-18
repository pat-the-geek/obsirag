from __future__ import annotations

import pytest

from src.ui.mermaid_streamlit import build_streamlit_chat_blocks, validate_mermaid


@pytest.mark.unit
class TestMermaidStreamlit:
    def test_validate_mermaid_rejects_forbidden_characters(self):
        with pytest.raises(ValueError, match="non ASCII"):
            validate_mermaid("flowchart TD\nA[Résumé] --> B")

    def test_build_streamlit_chat_blocks_falls_back_to_code_for_invalid_mermaid(self):
        blocks = build_streamlit_chat_blocks("Avant\n```mermaid\nflowchart TD\nA[Résumé] --> B\n```\nAprès")

        assert blocks == [
            ("text", "Avant\n"),
            ("mermaid_code", "flowchart TD\nA[Résumé] --> B"),
            ("text", "\nAprès"),
        ]

    def test_build_streamlit_chat_blocks_keeps_valid_mermaid_renderable(self):
        blocks = build_streamlit_chat_blocks("```mermaid\nflowchart TD\nA[Resume] --> B\n```")

        assert blocks == [("mermaid", "flowchart TD\nA[Resume] --> B")]