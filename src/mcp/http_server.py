from __future__ import annotations

import os
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, status

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


def build_server():
    """
    Construire le serveur FastMCP pour montage dans FastAPI.
    
    LAZY IMPORT — appelé dynamiquement pour éviter les boucles circulaires:
    http_server → tools → runtime → app (partiel)
    
    Donc on importe FastMCP et register_tools UNE FOIS quand mount_mcp_server()
    est appelé (à la fin du démarrage app).
    """
    from mcp.server.fastmcp import FastMCP
    from src.mcp.tools import register_tools
    
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
    
    Le serveur écoute sur <mount_path> via transport SSE.
    Les logs MCP sont capturés separément (pas stdout pollution).
    L'authentification se fait par Bearer token si auth_token est fourni.
    
    IMPORTANT: Cette fonction doit être appelée APRÈS avoir configuré tous les
    middlewares et routes de l'app FastAPI. Elle retourne immédiatement.
    Les requêtes MCP se font sur <mount_path>/sse et <mount_path>/messages.
    
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

    # En mode embarqué FastAPI, sse_app() est stable et n'exige pas run().
    mcp_app = server.sse_app()
    
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
                            content='{"error":"Missing Authorization header"}',
                            status_code=401,
                            media_type="application/json",
                        )
                    
                    if not auth_header.startswith("Bearer "):
                        return Response(
                            content='{"error":"Invalid Authorization format"}',
                            status_code=401,
                            media_type="application/json",
                        )
                    
                    token = auth_header[7:]
                    if token != auth_token:
                        return Response(
                            content='{"error":"Invalid token"}',
                            status_code=403,
                            media_type="application/json",
                        )
                
                return await call_next(request)
        
        app.add_middleware(MCPAuthMiddleware)
