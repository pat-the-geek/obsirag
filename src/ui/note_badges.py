from __future__ import annotations
import json
from pathlib import Path

_SHARED_COLORS: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent.parent.parent / "shared" / "note-type-colors.json").read_text()
)

_NOTE_TYPE_META: dict[str, dict[str, str]] = {
    "user":    {"label": "Note",    "icon": "📝", "graph_border": "#2563eb", "graph_highlight": "#93c5fd"},
    "report":  {"label": "Rapport", "icon": "📋", "graph_border": "#b45309", "graph_highlight": "#fcd34d"},
    "insight": {"label": "Insight", "icon": "💡", "graph_border": "#ca8a04", "graph_highlight": "#fde047"},
    "synapse": {"label": "Synapse", "icon": "⚡", "graph_border": "#9333ea", "graph_highlight": "#d8b4fe"},
    "entity":  {"label": "Entité",  "icon": "🏷️", "graph_border": "#059669", "graph_highlight": "#6ee7b7"},
}

_NOTE_TYPE_STYLES: dict[str, dict[str, str]] = {
    k: {
        **_NOTE_TYPE_META[k],
        "bg":         _SHARED_COLORS[k]["bg"],
        "border":     _SHARED_COLORS[k]["border"],
        "text":       _SHARED_COLORS[k]["text"],
        "graph_fill": _SHARED_COLORS[k]["fill"],
    }
    for k in _NOTE_TYPE_META
}

_NOTE_TYPE_ORDER = ["user", "report", "insight", "synapse", "entity"]


def get_note_type(file_path: str) -> str:
    normalized = file_path.replace("\\", "/").lower()
    if "/obsirag/insights/" in normalized or normalized.startswith("obsirag/insights/"):
        return "insight"
    if "/obsirag/synapses/" in normalized or normalized.startswith("obsirag/synapses/"):
        return "synapse"
    if "/obsirag/synthesis/" in normalized or normalized.startswith("obsirag/synthesis/"):
        return "report"
    if "/obsirag/entities/" in normalized or normalized.startswith("obsirag/entities/"):
        return "entity"
    # Dossiers "Rapports-*" créés par l'utilisateur (Rapports-WUDD-ai, Rapports-Claude, etc.)
    first_component = normalized.lstrip("/").split("/")[0]
    if first_component.startswith("rapports"):
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