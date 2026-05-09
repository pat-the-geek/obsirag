from __future__ import annotations

import os

# Désactive les services background (indexeur, autolearn, watcher) dans le processus MCP.
# Sans ce flag, ServiceManager démarre un thread _initial_index qui verrouille ChromaDB
# et bloque les requêtes graph/subgraph jusqu'à la fin de l'indexation complète.
os.environ.setdefault("OBSIRAG_MCP_MODE", "1")

from mcp.server.fastmcp import FastMCP

from src.mcp.tools import register_tools

SERVER_INSTRUCTIONS = (
    "Serveur MCP local pour ObsiRAG. "
    "Cette surface expose uniquement des outils read-only sur le coffre, "
    "le runtime systeme, le pipeline RAG et le graphe."
)


def build_server() -> FastMCP:
    server = FastMCP(
        name="ObsiRAG",
        instructions=SERVER_INSTRUCTIONS,
        log_level="INFO",
    )
    register_tools(server)
    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
