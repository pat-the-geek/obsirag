"""
Composant Streamlit bridge pour la communication iframe → Python.
Doit être importé (pas exécuté directement) pour que __name__ soit défini.
"""
import streamlit.components.v1 as components
from pathlib import Path

_bridge_dir = Path(__file__).parent / "note_bridge"
note_bridge = components.declare_component(
    "obsirag_note_bridge",
    path=str(_bridge_dir),
)
