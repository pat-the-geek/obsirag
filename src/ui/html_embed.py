from __future__ import annotations

import base64

import streamlit as st


def render_html_document(document: str, *, height: int) -> None:
    payload = base64.b64encode(document.encode("utf-8")).decode("ascii")
    st.iframe(f"data:text/html;base64,{payload}", height=height, width="stretch")


def run_inline_script(script: str) -> None:
    st.html(f"<script>{script}</script>", unsafe_allow_javascript=True)