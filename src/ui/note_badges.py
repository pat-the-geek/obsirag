from __future__ import annotations


_NOTE_TYPE_STYLES = {
    "user": {
        "label": "Note",
        "icon": "📝",
        "bg": "rgba(0, 102, 184, 0.12)",
        "border": "rgba(0, 102, 184, 0.28)",
        "text": "#0066b8",
        "graph_fill": "#60a5fa",
        "graph_border": "#2563eb",
        "graph_highlight": "#93c5fd",
    },
    "report": {
        "label": "Rapport",
        "icon": "📋",
        "bg": "rgba(180, 83, 9, 0.12)",
        "border": "rgba(180, 83, 9, 0.28)",
        "text": "#b45309",
        "graph_fill": "#f59e0b",
        "graph_border": "#b45309",
        "graph_highlight": "#fcd34d",
    },
    "insight": {
        "label": "Insight",
        "icon": "💡",
        "bg": "rgba(202, 138, 4, 0.12)",
        "border": "rgba(202, 138, 4, 0.28)",
        "text": "#a16207",
        "graph_fill": "#facc15",
        "graph_border": "#ca8a04",
        "graph_highlight": "#fde047",
    },
    "synapse": {
        "label": "Synapse",
        "icon": "⚡",
        "bg": "rgba(147, 51, 234, 0.12)",
        "border": "rgba(147, 51, 234, 0.28)",
        "text": "#7e22ce",
        "graph_fill": "#c084fc",
        "graph_border": "#9333ea",
        "graph_highlight": "#d8b4fe",
    },
}

_NOTE_TYPE_ORDER = ["user", "report", "insight", "synapse"]


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


def list_note_type_keys() -> list[str]:
    return list(_NOTE_TYPE_ORDER)


def get_note_type_options() -> list[dict[str, str]]:
    return [
        {"key": note_type, **_NOTE_TYPE_STYLES[note_type]}
        for note_type in _NOTE_TYPE_ORDER
    ]


def get_note_graph_color(file_path: str) -> dict[str, str | dict[str, str]]:
    meta = get_note_type_meta(file_path)
    return {
        "background": meta["graph_fill"],
        "border": meta["graph_border"],
        "highlight": {
            "background": meta["graph_highlight"],
            "border": meta["graph_border"],
        },
    }


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