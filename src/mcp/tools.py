from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp.runtime import (
    ask_rag_payload,
    get_graph_subgraph_payload,
    get_note_payload,
    get_system_status_payload,
    search_notes_payload,
)


def register_tools(server: FastMCP) -> None:
    @server.tool(
        name="obsirag_get_system_status",
        description="Retourne l'etat du runtime ObsiRAG, de l'indexation et des composants locaux.",
        structured_output=True,
    )
    def get_system_status() -> dict[str, Any]:
        """Lire le statut systeme local d'ObsiRAG."""
        return get_system_status_payload()

    @server.tool(
        name="obsirag_search_notes",
        description="Recherche des notes par titre ou chemin relatif dans le coffre indexe.",
        structured_output=True,
    )
    def search_notes(query: str, limit: int = 10) -> dict[str, Any]:
        """Chercher des notes pertinentes a partir d'un texte libre."""
        return search_notes_payload(query, limit=limit)

    @server.tool(
        name="obsirag_get_note",
        description="Retourne le detail d'une note Obsidian connue par son chemin ou son identifiant.",
        structured_output=True,
    )
    def get_note(note_path: str) -> dict[str, Any]:
        """Lire une note complete, avec contenu Markdown et metadonnees utiles."""
        return get_note_payload(note_path)

    @server.tool(
        name="obsirag_ask_rag",
        description=(
            "Pose une question RAG au coffre local. "
            "Par defaut utilise Ollama (LLM local). "
            "Activer use_euria=true pour utiliser le LLM cloud Euria (plus puissant). "
            "Activer web_search=true (requiert use_euria=true) pour enrichir la reponse via le web."
        ),
        structured_output=True,
    )
    def ask_rag(
        question: str,
        history: list[dict[str, str]] | None = None,
        exclude_obsirag_generated: bool = False,
        use_euria: bool = False,
        web_search: bool = False,
    ) -> dict[str, Any]:
        """Interroger le coffre via le pipeline RAG local d'ObsiRAG."""
        return ask_rag_payload(
            question,
            history=history,
            exclude_obsirag_generated=exclude_obsirag_generated,
            use_euria=use_euria,
            web_search=web_search,
        )

    @server.tool(
        name="obsirag_get_graph_subgraph",
        description="Retourne un sous-graphe local autour d'une note du coffre indexe.",
        structured_output=True,
    )
    def get_graph_subgraph(
        note_id: str,
        depth: int = 1,
        folders: list[str] | None = None,
        tags: list[str] | None = None,
        note_types: list[str] | None = None,
        search_text: str = "",
        recency_days: int | None = None,
    ) -> dict[str, Any]:
        """Explorer le graphe local autour d'une note, avec filtres optionnels."""
        return get_graph_subgraph_payload(
            note_id,
            depth=depth,
            folders=folders,
            tags=tags,
            note_types=note_types,
            search_text=search_text,
            recency_days=recency_days,
        )
