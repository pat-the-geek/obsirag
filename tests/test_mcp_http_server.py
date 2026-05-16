"""
Tests pour le serveur MCP HTTP (SSE).

Notes:
- Ce test monte le serveur MCP sur une app FastAPI de test
- Vérifie que les routes /mcp/* sont accessibles
- Vérifie l'auth Bearer token si configurée
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.mcp.http_server import mount_mcp_server


@pytest.fixture
def app_without_auth() -> FastAPI:
    """FastAPI app avec MCP monté sans auth."""
    app = FastAPI(title="Test App")
    mount_mcp_server(app, auth_token=None, mount_path="/mcp")
    return app


@pytest.fixture
def app_with_auth() -> FastAPI:
    """FastAPI app avec MCP monté avec auth Bearer."""
    app = FastAPI(title="Test App")
    mount_mcp_server(app, auth_token="sk-test-token", mount_path="/mcp")
    return app


def test_mcp_initialize_without_auth(app_without_auth):
    """Test initialize MCP sans authentification."""
    client = TestClient(app_without_auth)
    
    response = client.post(
        "/mcp/initialize",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0"
                }
            }
        }
    )
    
    # Initialize doit répondre
    assert response.status_code == 200
    data = response.json()
    assert data.get("id") == 1
    assert "result" in data or "error" in data


def test_mcp_initialize_with_auth_missing_token(app_with_auth):
    """Test initialize MCP sans Bearer token (doit échouer)."""
    client = TestClient(app_with_auth)
    
    response = client.post(
        "/mcp/initialize",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0"
                }
            }
        }
    )
    
    # Doit retourner 401 ou réponse d'erreur MCP
    # (middleware peut faire 401 HTTP ou réponse JSON-RPC error)
    assert response.status_code in (401, 200)
    if response.status_code == 200:
        data = response.json()
        assert "error" in data


def test_mcp_initialize_with_auth_invalid_token(app_with_auth):
    """Test initialize MCP avec mauvais token (doit échouer)."""
    client = TestClient(app_with_auth)
    
    response = client.post(
        "/mcp/initialize",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0"
                }
            }
        },
        headers={"Authorization": "Bearer invalid-token"}
    )
    
    # Doit retourner 403 ou erreur
    assert response.status_code in (403, 401, 200)
    if response.status_code == 200:
        data = response.json()
        assert "error" in data


def test_mcp_initialize_with_auth_valid_token(app_with_auth):
    """Test initialize MCP avec bon token (doit réussir)."""
    client = TestClient(app_with_auth)
    
    response = client.post(
        "/mcp/initialize",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0"
                }
            }
        },
        headers={"Authorization": "Bearer sk-test-token"}
    )
    
    # Doit répondre 200
    assert response.status_code == 200
    data = response.json()
    assert data.get("id") == 1
