from __future__ import annotations


_NOTE_TYPE_STYLES = {
    "user": {
        "label": "Note",
        "icon": "📝",
        "bg": "rgba(0, 102, 184, 0.12)",
        "border": "rgba(0, 102, 184, 0.28)",
        "text": "#0066b8",
    },
    "report": {
        "label": "Rapport",
        "icon": "📋",
        "bg": "rgba(180, 83, 9, 0.12)",
        "border": "rgba(180, 83, 9, 0.28)",
        "text": "#b45309",
    },
    "insight": {
        "label": "Insight",
        "icon": "💡",
        "bg": "rgba(202, 138, 4, 0.12)",
        "border": "rgba(202, 138, 4, 0.28)",
        "text": "#a16207",
    },
    "synapse": {
        "label": "Synapse",
        "icon": "⚡",
        "bg": "rgba(147, 51, 234, 0.12)",
        "border": "rgba(147, 51, 234, 0.28)",
        "text": "#7e22ce",
    },
}


def get_note_type(file_path: str) -> str:
    normalized = file_path.replace("\\", "/").lower()
    if "/obsirag/insights/" in normalized or normalized.startswith("obsirag/insights/"):
        return "insight"
    if "/obsirag/synapses/" in normalized or normalized.startswith("obsirag/synapses/"):
        return "synapse"
    if "/obsirag/synthesis/" in normalized or normalized.startswith("obsirag/synthesis/"):
        return "report"
    return "user"


def get_note_type_meta(file_path: str) -> dict[str, str]:
    note_type = get_note_type(file_path)
    return {"key": note_type, **_NOTE_TYPE_STYLES[note_type]}


def render_note_badge(file_path: str) -> str:
    meta = get_note_type_meta(file_path)
    return (
        f"<span style=\"display:inline-flex;align-items:center;gap:0.35rem;"
        f"padding:0.16rem 0.52rem;border-radius:999px;font-size:0.75rem;font-weight:700;"
        f"background:{meta['bg']};border:1px solid {meta['border']};color:{meta['text']};\">"
        f"<span>{meta['icon']}</span><span>{meta['label']}</span></span>"
    )


def prefix_note_label(title: str, file_path: str) -> str:
    meta = get_note_type_meta(file_path)
    return f"{meta['icon']} {meta['label']} · {title}"