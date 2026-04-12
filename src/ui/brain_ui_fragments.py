from __future__ import annotations

from html import escape


def build_brain_page_header_html(brain_icon_b64: str) -> str:
    return (
        "<h1 style='display:flex;align-items:center;gap:8px'>"
        f"<img src='data:image/svg+xml;base64,{brain_icon_b64}' width='96' height='96'>"
        "Cerveau</h1>"
    )


def build_badge_row_html(badges_html: list[str]) -> str:
    return "<div style='display:flex;gap:0.5rem;flex-wrap:wrap;'>" + "".join(badges_html) + "</div>"


def build_brain_note_row_html(note_badge_html: str, title: str, subtitle: str) -> str:
    return (
        "<div style='display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;'>"
        f"{note_badge_html}"
        f"<strong>{escape(title)}</strong>"
        f"<span style='opacity:.72;'>{escape(subtitle)}</span>"
        "</div>"
    )