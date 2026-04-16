from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from src.ui.html_embed import render_html_document, run_inline_script


@pytest.mark.unit
class TestHtmlEmbed:
    def test_render_html_document_uses_base64_data_url(self):
        document = "<html><body><h1>Demo</h1></body></html>"

        with patch("src.ui.html_embed.st.iframe") as iframe:
            render_html_document(document, height=320)

        iframe.assert_called_once()
        args, kwargs = iframe.call_args
        assert args[0].startswith("data:text/html;base64,")
        payload = args[0].split(",", 1)[1]
        assert base64.b64decode(payload).decode("utf-8") == document
        assert kwargs == {"height": 320, "width": "stretch"}

    def test_run_inline_script_wraps_script_tag_and_enables_javascript(self):
        script = "console.log('demo');"

        with patch("src.ui.html_embed.st.html") as html:
            run_inline_script(script)

        html.assert_called_once_with(
            "<script>console.log('demo');</script>",
            unsafe_allow_javascript=True,
        )

    def test_render_html_document_can_use_inline_transport(self):
        document = "<div id='graph'></div><script>console.log('graph');</script>"

        with patch("src.ui.html_embed.st.html") as html:
            render_html_document(document, height=320, transport="inline")

        html.assert_called_once_with(
            document,
            width="stretch",
            unsafe_allow_javascript=True,
        )

    def test_render_html_document_can_use_srcdoc_transport(self):
        document = "<html><body><script>console.log(\"graph\")</script></body></html>"

        with patch("src.ui.html_embed.st.html") as html_mock:
            render_html_document(document, height=320, transport="srcdoc")

        html_mock.assert_called_once()
        args, kwargs = html_mock.call_args
        assert "<iframe" in args[0]
        assert 'sandbox="allow-scripts allow-same-origin allow-popups"' in args[0]
        assert 'height:320px' in args[0]
        assert "srcdoc=" in args[0]
        assert "<script>" not in args[0]
        assert "&lt;script&gt;" in args[0]
        assert "&quot;graph&quot;" in args[0]
        assert kwargs == {"width": "stretch"}

    def test_render_html_document_can_use_component_transport(self):
        document = "<html><body><script>console.log('graph')</script></body></html>"

        with patch("src.ui.html_embed.st_components.html") as component_html:
            render_html_document(document, height=320, transport="component")

        component_html.assert_called_once_with(document, height=320, scrolling=False)