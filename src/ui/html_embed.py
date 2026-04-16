from __future__ import annotations

import base64
import html
from typing import Literal

import streamlit as st
import streamlit.components.v1 as st_components


def render_html_document(
    document: str,
    *,
    height: int,
    transport: Literal["iframe", "inline", "srcdoc", "component"] = "iframe",
) -> None:
    if transport == "inline":
        st.html(document, width="stretch", unsafe_allow_javascript=True)
        return

    if transport == "component":
        st_components.html(document, height=height, scrolling=False)
        return

    if transport == "srcdoc":
        escaped_document = html.escape(document, quote=True)
        iframe = (
            f'<iframe sandbox="allow-scripts allow-same-origin allow-popups" '
            f'style="width:100%;height:{height}px;border:0;overflow:hidden;" '
            f'srcdoc="{escaped_document}"></iframe>'
        )
        st.html(iframe, width="stretch")
        return

    payload = base64.b64encode(document.encode("utf-8")).decode("ascii")
    st.iframe(f"data:text/html;base64,{payload}", height=height, width="stretch")


def run_inline_script(script: str) -> None:
    st.html(f"<script>{script}</script>", unsafe_allow_javascript=True)
