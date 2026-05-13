from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp.runtime import (
    ask_rag_payload,
    browse_notes_by_date_payload,
    conversation_continue_payload,
    conversation_finalize_payload,
    conversation_start_payload,
    get_entity_stats_payload,
    get_graph_subgraph_payload,
    get_note_payload,
    get_system_status_payload,
    list_folder_payload,
    search_notes_payload,
    search_notes_semantic_payload,
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
            "Démarre une investigation conversationnelle multi-tours dans le coffre. "
            "À utiliser dès qu'une question mérite d'être creusée sous plusieurs angles : "
            "réponse incomplète ou vague d'obsirag_ask_rag, sources contradictoires, "
            "concept à explorer en profondeur, sujet que le coffre ne couvre qu'en partie, "
            "ou branche thématique inattendue à explorer. "
            "L'investigation est persistée sous forme de note dans le coffre. "
            "Une seule conversation active à la fois — appeler obsirag_conversation_finalize avant d'en ouvrir une nouvelle. "
            "trigger_reason : sentinel_response | low_confidence | incomplete_coverage | "
            "contradictory_sources | unexpected_primary_source | branch_exploration."
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
            "Poursuit une investigation active avec une nouvelle question RAG. "
            "Chaque tour doit approfondir un angle différent : chercher des preuves contraires, "
            "explorer un sous-thème identifié au tour précédent, confirmer une hypothèse, "
            "ou élargir à un concept connexe dans le coffre. "
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
            "Clôt une conversation d'investigation et écrit la synthèse finale dans le coffre. "
            "Doit toujours être appelé après obsirag_conversation_continue (quand turns_remaining == 0) "
            "ou pour fermer une investigation incomplète. "
            "resolved=true si l'investigation a abouti à une conclusion claire, false sinon."
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
        name="obsirag_browse_notes_by_date",
        description=(
            "Liste les notes du coffre triées par date de modification décroissante. "
            "Permet de trouver les N dernières notes modifiées, ou de filtrer sur une période. "
            "date_from et date_to acceptent le format YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS. "
            "folders filtre par dossier (ex: ['Journal', 'Projets/Alpha']). "
            "tags filtre par tag Obsidian (ex: ['ia', 'lecture']). "
            "Les notes générées par ObsiRAG (insights, synapses) sont exclues par défaut."
        ),
        structured_output=True,
    )
    def browse_notes_by_date(
        limit: int = 10,
        date_from: str | None = None,
        date_to: str | None = None,
        folders: list[str] | None = None,
        tags: list[str] | None = None,
        exclude_obsirag_generated: bool = True,
    ) -> dict[str, Any]:
        """Parcourir les notes par date, avec filtres optionnels de période, dossier et tag."""
        return browse_notes_by_date_payload(
            limit=limit,
            date_from=date_from,
            date_to=date_to,
            folders=folders,
            tags=tags,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )

    @server.tool(
        name="obsirag_search_notes_semantic",
        description=(
            "Recherche des notes par similarité sémantique sur le contenu complet (corps + titre). "
            "Contrairement à obsirag_search_notes (titre/chemin uniquement), cet outil retrouve "
            "des notes dont le sens est proche de la requête, même sans correspondance lexicale exacte. "
            "Exemple : 'impact des écrans sur le sommeil' retrouve une note sur la lumière bleue. "
            "Retourne les notes avec score de similarité et un extrait du passage le plus pertinent. "
            "exclude_obsirag_generated=true exclut les insights et synapses générés automatiquement."
        ),
        structured_output=True,
    )
    def search_notes_semantic(
        query: str,
        limit: int = 10,
        exclude_obsirag_generated: bool = True,
    ) -> dict[str, Any]:
        """Rechercher des notes par similarité sémantique sur leur contenu."""
        return search_notes_semantic_payload(
            query=query,
            limit=limit,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )

    @server.tool(
        name="obsirag_get_entity_stats",
        description=(
            "Retourne les entités nommées les plus fréquentes dans le coffre (personnes, organisations, lieux). "
            "Permet de cartographier les thèmes principaux : qui est le plus mentionné, quelles organisations, "
            "quels lieux. entity_type filtre par type : 'persons', 'orgs', 'locations', 'misc', ou 'all'. "
            "top_n contrôle le nombre d'entités retournées par type (défaut 30, max 100)."
        ),
        structured_output=True,
    )
    def get_entity_stats(
        top_n: int = 30,
        entity_type: str = "all",
    ) -> dict[str, Any]:
        """Obtenir la cartographie thématique des entités nommées du coffre."""
        return get_entity_stats_payload(top_n=top_n, entity_type=entity_type)

    @server.tool(
        name="obsirag_list_folder",
        description=(
            "Liste toutes les notes d'un dossier du coffre, triées par date de modification décroissante. "
            "folder_path est le chemin relatif du dossier dans le coffre (ex: 'Idees/Épanouissement', 'Journal'). "
            "Préférer cet outil à obsirag_browse_notes_by_date quand l'intention est d'explorer un dossier précis. "
            "exclude_obsirag_generated=true exclut les insights et synapses (activé par défaut)."
        ),
        structured_output=True,
    )
    def list_folder(
        folder_path: str,
        limit: int = 50,
        exclude_obsirag_generated: bool = True,
    ) -> dict[str, Any]:
        """Lister toutes les notes d'un dossier du coffre."""
        return list_folder_payload(
            folder_path=folder_path,
            limit=limit,
            exclude_obsirag_generated=exclude_obsirag_generated,
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
