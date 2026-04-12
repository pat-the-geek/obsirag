from __future__ import annotations

from html import escape


def build_obsidian_open_link_html(obsidian_url: str) -> str:
    safe_url = escape(obsidian_url, quote=True)
    return (
        f'<a href="{safe_url}" target="_blank" style="'
        "display:inline-flex;align-items:center;gap:6px;"
        "background:#7C3AED;color:#fff;border-radius:6px;"
        "padding:4px 12px;font-size:13px;font-weight:600;"
        'text-decoration:none;">'
        "🟣 Ouvrir dans Obsidian</a>"
    )


def build_outline_item_html(title: str, line: int, level: int) -> str:
    indent = "&nbsp;" * max(0, (int(level) - 1) * 4)
    return (
        f"{indent}<strong>{escape(title)}</strong> "
        f"<span style='opacity:.6'>(ligne {int(line)})</span>"
    )


def build_search_match_html(section: str, line: int, snippet: str) -> str:
    return (
        f"<strong>{escape(section)}</strong> · ligne {int(line)}<br>"
        f"{escape(snippet)}"
    )