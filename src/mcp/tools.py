from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp.runtime import (
    ask_rag_payload,
    conversation_continue_payload,
    conversation_finalize_payload,
    conversation_start_payload,
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
            "Pose une question RAG au coffre local (Ollama par defaut). "
            "Quand le coffre ne contient pas la reponse (sentinelle Ollama), "
            "ObsiRAG bascule automatiquement sur Euria+recherche web si Euria est configure "
            "— le champ provider indique quel LLM a repondu ('ollama' ou 'euria+web'). "
            "Forcer use_euria=true pour utiliser Euria directement sans passer par Ollama. "
            "Si suggestEuriaWebSearch=true dans la reponse, Euria n'etait pas disponible "
            "et une relance manuelle avec use_euria=true web_search=true est recommandee."
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
        name="obsirag_conversation_start",
        description=(
            "Crée une conversation d'investigation et exécute le premier tour de question/réponse. "
            "A utiliser uniquement pour vérifier la qualité d'une réponse de obsirag_ask_rag. "
            "Une seule conversation active à la fois. "
            "trigger_reason doit être l'une des valeurs : sentinel_response, low_confidence, "
            "incomplete_coverage, contradictory_sources, unexpected_primary_source, branch_exploration."
        ),
        structured_output=True,
    )
    def conversation_start(
        title: str,
        triggering_question: str,
        trigger_reason: str,
        trigger_explanation: str,
        initial_rag_response: dict,
        first_followup_question: str,
    ) -> dict[str, Any]:
        """Démarrer une investigation conversationnelle persistée dans le coffre."""
        return conversation_start_payload(
            title=title,
            triggering_question=triggering_question,
            trigger_reason=trigger_reason,
            trigger_explanation=trigger_explanation,
            initial_rag_response=initial_rag_response,
            first_followup_question=first_followup_question,
        )

    @server.tool(
        name="obsirag_conversation_continue",
        description=(
            "Ajoute un tour à une conversation d'investigation active. "
            "Exécute une question RAG et l'appende à la note. "
            "Maximum 3 tours après obsirag_conversation_start. "
            "Quand turns_remaining == 0, appeler obsirag_conversation_finalize."
        ),
        structured_output=True,
    )
    def conversation_continue(
        conversation_id: str,
        question: str,
        reasoning: str,
    ) -> dict[str, Any]:
        """Continuer une investigation en ajoutant un tour de Q&R."""
        return conversation_continue_payload(
            conversation_id=conversation_id,
            question=question,
            reasoning=reasoning,
        )

    @server.tool(
        name="obsirag_conversation_finalize",
        description=(
            "Clôt définitivement une conversation d'investigation. "
            "Écrit la synthèse finale dans la note et marque status: closed. "
            "Doit être appelé avant d'en démarrer une nouvelle."
        ),
        structured_output=True,
    )
    def conversation_finalize(
        conversation_id: str,
        final_synthesis: str,
        resolved: bool,
    ) -> dict[str, Any]:
        """Clôturer une investigation et écrire la synthèse finale."""
        return conversation_finalize_payload(
            conversation_id=conversation_id,
            final_synthesis=final_synthesis,
            resolved=resolved,
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
