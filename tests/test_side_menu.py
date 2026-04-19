from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import patch

import pytest

from src.ui.side_menu import render_mobile_main_menu


@pytest.mark.unit
class TestSideMenu:
    def test_render_mobile_main_menu_uses_page_link_for_internal_navigation(self):
        with patch("src.ui.side_menu.st.markdown"):
            with patch("src.ui.side_menu.st.container", return_value=nullcontext()):
                with patch("src.ui.side_menu.st.expander", return_value=nullcontext()) as expander:
                    with patch("src.ui.side_menu.st.caption") as caption:
                        with patch("src.ui.side_menu.st.page_link") as page_link:
                            render_mobile_main_menu()

        expander.assert_called_once_with("☰", expanded=False, width="stretch")
        caption.assert_called_once_with("Navigation")
        assert page_link.call_count == 5
        called_pages = [call.args[0] for call in page_link.call_args_list]
        assert called_pages == [
            "pages/0_Dashboard.py",
            "app.py",
            "pages/1_Brain.py",
            "pages/2_Insights.py",
            "pages/3_Settings.py",
        ]

    def test_render_mobile_main_menu_scopes_css_to_keyed_container(self):
        with patch("src.ui.side_menu.st.markdown") as markdown:
            with patch("src.ui.side_menu.st.container", return_value=nullcontext()):
                with patch("src.ui.side_menu.st.expander", return_value=nullcontext()):
                    with patch("src.ui.side_menu.st.caption"):
                        with patch("src.ui.side_menu.st.page_link"):
                            render_mobile_main_menu()

        css = markdown.call_args.args[0]
        assert ".st-key-obsirag-mobile-menu" in css
        assert "data-testid=\"stPageLink\"" in css
        assert "data-testid=\"stExpander\"" in css
        assert "href=\"/Dashboard\"" not in css
        assert "{{" not in css
        assert "}}" not in css