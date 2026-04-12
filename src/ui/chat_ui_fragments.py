from __future__ import annotations

from html import escape


def build_primary_source_html(note_title: str, note_badge_html: str) -> str:
    return (
        "<div style='margin:0.2rem 0 0.5rem 0;display:flex;align-items:center;gap:0.5rem;'>"
        "<span style='font-size:0.85rem;color:inherit;'>🎯 Note principale :</span>"
        f"{note_badge_html}"
        f"<strong>{escape(note_title)}</strong>"
        "</div>"
    )


def build_source_entry_html(
    note_title: str,
    note_badge_html: str,
    date_modified: str,
    score: float,
    is_primary: bool,
) -> str:
    primary_badge = " · Principale" if is_primary else ""
    date_label = escape((date_modified or "")[:10])
    return (
        "<div style='display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;'>"
        f"{note_badge_html}"
        f"<strong>{escape(note_title)}</strong>"
        f"<span style='opacity:.72;font-size:0.82rem;'>{primary_badge} · {date_label} · Score {score:.2f}</span>"
        "</div>"
    )


def build_user_bubble_html(text: str, avatar_svg: str) -> str:
    escaped = escape(text)
    return (
        '<div style="display:flex;justify-content:flex-end;align-items:flex-start;'
        'gap:8px;margin:6px 0;padding:0 2px;width:100%">'
        '<div style="max-width:75%;'
        'background:var(--user-bubble-bg,#264f78);'
        'border:1px solid var(--user-bubble-border,#569cd6);'
        'border-radius:14px 4px 14px 14px;'
        'padding:10px 14px;'
        'color:var(--text-color,#d4d4d4);'
        'font-size:0.95rem;line-height:1.5;word-break:break-word">'
        f"{escaped}</div>"
        '<div style="flex-shrink:0;margin-top:1px;filter:drop-shadow(0 1px 3px rgba(124,58,237,0.4))">'
        f"{avatar_svg}</div>"
        "</div>"
    )


def build_sidebar_header_html(icon_b64: str) -> str:
    return (
        "<h2 style='display:flex;align-items:center;gap:10px;margin:0'>"
        f"<img src='data:image/png;base64,{icon_b64}' width='96' style='border-radius:4px'>"
        "ObsiRAG</h2>"
    )


def build_generation_status_caption(token_count: int, ttft: float, total: float, tps: float) -> str:
    return (
        f"✅ {token_count} tokens · "
        f"TTFT {ttft:.1f}s · "
        f"{total:.1f}s total · "
        f"{tps:.0f} tok/s"
    )


def build_message_stats_caption(token_count: int, ttft: float, total: float, tps: float) -> str:
    """Caption de stats pour un message historique (⚡, distinct du statut live ✅)."""
    return (
        f"⚡ {token_count} tokens · "
        f"TTFT {ttft:.1f}s · "
        f"{total:.1f}s total · "
        f"{tps:.0f} tok/s"
    )


def build_cited_source_row_html(note_title: str, note_badge_html: str) -> str:
    return (
        "<div style='display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;'>"
        f"{note_badge_html}"
        f"<strong>{escape(note_title)}</strong>"
        "</div>"
    )