"""
MCP HTTP Server (SSE) — Intégration FastMCP dans FastAPI.

Remplace le transport stdio par streamable-http pour éviter les timeouts initialize
et permettre un process MCP persistant sans logs sur stdout.

Utilisation dans FastAPI:
    from src.mcp.http_server import mount_mcp_server
    mount_mcp_server(app, auth_token=settings.mcp_auth_token)

L'authentification se fait par Bearer token sur toutes les routes /mcp/*.

Exemple client MCP:
    curl -X POST http://localhost:8081/mcp/initialize \\
      -H "Authorization: Bearer your-token" \\
      -H "Content-Type: application/json" \\
      -d '{
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
          "protocolVersion": "2024-11-05",
          "capabilities": {},
          "clientInfo": {"name": "claude", "version": "1.0"}
        }
      }'
"""

from __future__ import annotations

import os
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, status
from mcp.server.fastmcp import FastMCP

from src.mcp.tools import register_tools

# Désactive les services background (indexeur, autolearn, watcher) dans le processus MCP.
# Sans ce flag, ServiceManager démarre un thread _initial_index qui verrouille ChromaDB
# et bloque les requêtes graph/subgraph jusqu'à la fin de l'indexation complète.
os.environ.setdefault("OBSIRAG_MCP_MODE", "1")

SERVER_INSTRUCTIONS = (
    "Serveur MCP HTTP (SSE) pour ObsiRAG. "
    "Cette surface expose uniquement des outils read-only sur le coffre, "
    "le runtime système, le pipeline RAG et le graphe. "
    "Authentification: Bearer token dans Authorization header."
)


def build_server() -> FastMCP:
    """Construire le serveur FastMCP pour montage dans FastAPI."""
    server = FastMCP(
        name="ObsiRAG",
        instructions=SERVER_INSTRUCTIONS,
        log_level="INFO",
    )
    register_tools(server)
    return server


def create_auth_dependency(expected_token: str | None) -> Callable[[str | None], None]:
    """
    Créer une dépendance FastAPI pour valider le Bearer token.
    
    Args:
        expected_token: Token attendu. Si None, auth désactivée.
    
    Returns:
        Fonction de dépendance FastAPI
    """
    async def verify_token(authorization: str | None = Header(None)) -> None:
        if expected_token is None:
            # Auth désactivée
            return
        
        if authorization is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
            )
        
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header must be 'Bearer <token>'",
            )
        
        token = authorization[7:]  # Strip "Bearer "
        if token != expected_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid token",
            )
    
    return verify_token


def mount_mcp_server(
    app: FastAPI,
    auth_token: str | None = None,
    mount_path: str = "/mcp",
) -> None:
    """
    Monter le serveur MCP HTTP (SSE) sur une application FastAPI.
    
    Le serveur écoute sur <mount_path>/* (ex: /mcp/initialize, /mcp/call_tool, etc).
    Les logs MCP sont captés separément (pas stdout pollution).
    L'authentification se fait par Bearer token si auth_token est fourni.
    
    IMPORTANT: Cette fonction doit être appelée APRÈS avoir configurer tous les
    middlewares et routes de l'app FastAPI. Elle retourne immédiatement.
    Les requêtes MCP se font sur les routes <mount_path>/*.
    
    Args:
        app: Application FastAPI
        auth_token: Token d'authentification Bearer. Si None, auth désactivée.
        mount_path: Racine des routes MCP (défaut: /mcp)
    
    Example:
        from src.mcp.http_server import mount_mcp_server
        from src.config import settings
        
        app = FastAPI()
        # ... setup app ...
        mount_mcp_server(app, auth_token=settings.mcp_auth_token)
    """
    server = build_server()
    
    # FastMCP.streamable_http_app est une ASGI app prête à monter
    mcp_app = server.streamable_http_app
    
    # Monter l'app MCP sur FastAPI avec le préfixe
    app.mount(mount_path, mcp_app)
    
    # Si auth_token est configuré, ajouter un middleware d'authentification
    # pour les routes /mcp/*
    if auth_token:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import Response
        
        class MCPAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next) -> Response:
                # Vérifier l'auth seulement pour les routes /mcp/*
                if request.url.path.startswith(mount_path):
                    auth_header = request.headers.get("authorization")
                    
                    if not auth_header:
                        return Response(
                            content='{"jsonrpc":"2.0","error":{"code":-32600,"message":"Missing Authorization header"}}',
                            status_code=401,
                            media_type="application/json",
                        )
                    
                    if not auth_header.startswith("Bearer "):
                        return Response(
                            content='{"jsonrpc":"2.0","error":{"code":-32600,"message":"Invalid Authorization format"}}',
                            status_code=401,
                            media_type="application/json",
                        )
                    
                    token = auth_header[7:]
                    if token != auth_token:
                        return Response(
                            content='{"jsonrpc":"2.0","error":{"code":-32600,"message":"Invalid token"}}',
                            status_code=403,
                            media_type="application/json",
                        )
                
                return await call_next(request)
        
        app.add_middleware(MCPAuthMiddleware)
