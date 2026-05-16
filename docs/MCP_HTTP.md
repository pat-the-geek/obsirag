# ObsiRAG MCP Server (HTTP SSE)

## Overview

ObsiRAG expose un **serveur MCP (Model Context Protocol) natif via HTTP SSE** sur la route `/mcp`, intégré directement dans FastAPI. Remplace le transport stdio legacy pour une meilleure stabilité et performance.

**Avantages par rapport au stdio:**
- ✅ **Aucun timeout initialize** — réponse < 500ms, pas de subprocess
- ✅ **Process persistant** — lancé une seule fois avec le backend FastAPI
- ✅ **Logs propres** — pas de pollution stdout
- ✅ **Auth Bearer token** — sécurisé, documenté
- ✅ **Scalable** — support multi-client concurrent

## Configuration

### Token d'authentification

Ajouter dans `.env`:
```bash
MCP_AUTH_TOKEN=sk-obsirag-xxxxxxxxxxxxx
```

Si non défini → MCP accessible **sans authentification**.

### Lancement

Aucune action supplémentaire : MCP est lancé automatiquement avec `./start.sh`.

```bash
./start.sh              # Démarrage FastAPI + Expo + MCP sur http://localhost:8081
```

## Utilisation Client

### Format URL

```
http://localhost:8081/mcp
```

Transport HTTP actif:

- `GET /mcp/sse` pour ouvrir le flux SSE
- `POST /mcp/messages/?session_id=...` pour envoyer les requêtes JSON-RPC

### Authentification

```bash
Authorization: Bearer sk-obsirag-xxxxxxxxxxxxx
Content-Type: application/json
```

### Requête MCP JSON-RPC 2.0

#### Smoke test automatisé

```bash
python scripts/mcp_smoke_test.py --base-url http://localhost:8081
# Avec auth:
python scripts/mcp_smoke_test.py \
  --base-url http://localhost:8081 \
  --auth-token "sk-obsirag-xxxxxxxxxxxxx"
```

#### Flux manuel SSE

1. Ouvrir `GET /mcp/sse`
2. Lire `event: endpoint` et `data: /mcp/messages/?session_id=...`
3. Poster initialize/tools/list/tools/call sur l'URL `messages`

#### Initialize

```bash
curl -N http://localhost:8081/mcp/sse
# event: endpoint
# data: /mcp/messages/?session_id=abc123...

curl -X POST "http://localhost:8081/mcp/messages/?session_id=abc123..." \
  -H "Authorization: Bearer sk-obsirag-xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "claude",
        "version": "1.0"
      }
    }
  }'
```

La requête retourne `202 Accepted`. La réponse JSON-RPC est envoyée sur le flux SSE ouvert.

**Réponse JSON-RPC attendue (sur SSE):**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {}
    },
    "serverInfo": {
      "name": "ObsiRAG",
      "version": "0.1.0"
    }
  }
}
```

#### List Tools

```bash
curl -X POST "http://localhost:8081/mcp/messages/?session_id=abc123..." \
  -H "Authorization: Bearer sk-obsirag-xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }'
```

#### Call Tool

```bash
curl -X POST "http://localhost:8081/mcp/messages/?session_id=abc123..." \
  -H "Authorization: Bearer sk-obsirag-xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "obsirag_get_system_status"
    }
  }'
```

## Outils disponibles

ObsiRAG MCP expose les outils read-only suivants:

| Outil | Description |
|-------|-------------|
| `obsirag_get_system_status` | État du runtime (indexation, composants) |
| `obsirag_search_notes` | Recherche par titre/chemin |
| `obsirag_search_notes_semantic` | Recherche vectorielle |
| `obsirag_get_note` | Détail complet d'une note |
| `obsirag_ask_rag` | Pipeline RAG local |
| `obsirag_conversation_start` | Démarrer investigation multi-tours |
| `obsirag_conversation_continue` | Continuer investigation |
| `obsirag_conversation_finalize` | Clôturer investigation |
| `obsirag_get_graph_filters` | Options filtres graphe |
| `obsirag_get_graph_subgraph` | Subgraphes thématiques |
| `obsirag_get_entity_stats` | Statistiques entités NER |
| `obsirag_list_folder` | Énumération dossiers |
| `obsirag_browse_notes_by_date` | Notes par date |

## Integration Claude Desktop

### Configuration `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsirag": {
      "url": "http://localhost:8081/mcp",
      "auth": {
        "type": "bearer",
        "token": "sk-obsirag-xxxxxxxxxxxxx"
      }
    }
  }
}
```

**Chemin sur macOS:**
```bash
~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Vérification

```bash
# Voir les logs Claude Desktop
log stream --predicate 'eventMessage contains[cd] "obsirag"' --level debug
```

## Architecture

```
FastAPI (port 8081)
  ├─ /api/v1/* (API REST classique)
  ├─ /mcp/* (MCP Server SSE)  ← NOUVEAU
  └─ / (Expo web static)
```

Le serveur MCP est une **ASGI app autonome montée sur FastAPI**, utilisant le transport FastMCP `sse`.

### Performance

- **Initialize:** < 100ms (mesure réelle, vs 5-30s en stdio subprocess)
- **Tool calls:** ~200-500ms (réseau + backend)
- **Concurrence:** Supporte clients multiples simultanés
- **Persistance:** Pas de reload entre requêtes

## Dépannage

### 401 Unauthorized

```
Missing Authorization header
```

**Fix:** Ajouter `-H "Authorization: Bearer sk-obsirag-xxxxxxxxxxxxx"`

### 403 Forbidden

```
Invalid token
```

**Fix:** Vérifier que `MCP_AUTH_TOKEN` en `.env` correspond au token client.

### Connection refused

```
curl: (7) Failed to connect to localhost port 8081: Connection refused
```

**Fix:** Vérifier que FastAPI est lancé.

```bash
./status.sh
```

### Logs MCP

Les logs MCP sont capturés par la `loguru` d'ObsiRAG, fichier:

```bash
tail -f logs/obsirag.log | grep MCP
```

Pour debug détaillé:
```bash
LOG_LEVEL=DEBUG ./start.sh
```

## Backward Compatibility

Le transport **stdio historique** est conservé pour usages legacy:

```bash
# Lancer MCP en stdio (mode classique, déprécié)
python -m src.mcp.server
```

Mais **la production utilise HTTP** (`./start.sh`).

## Voir aussi

- [Architecture MCP](https://modelcontextprotocol.io/spec)
- [FastMCP docs](https://github.com/jLorenzen/fastmcp)
- [ObsiRAG Architecture](./architecture.md)
