"""
Singleton Streamlit des services ObsiRAG.
Importé par toutes les pages pour accéder aux services.
"""
import streamlit as st
from src.services import ServiceManager


@st.cache_resource(show_spinner="Démarrage des services ObsiRAG…")
def get_services() -> ServiceManager:
    return ServiceManager()
