# MCP HTTP Quick-Start

## 1. Générer un token (optionnel)

```bash
# Générer un token Bearer aléatoire
openssl rand -hex 32 | sed 's/^/sk-obsirag-/'
# Exemple: sk-obsirag-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

## 2. Configurer dans `.env`

```env
# Optionnel — si vous voulez authentifier MCP
MCP_AUTH_TOKEN=sk-obsirag-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

Si non défini, MCP est public (accessible sans token).

## 3. Démarrer ObsiRAG

```bash
./start.sh
# Logs:
# API backend: UP sur 8080 (local) ou 8081 (Docker)
# Expo web: UP sur 8081
# MCP HTTP: http://localhost:8081/mcp
```

## 4. Tester MCP

### Smoke test automatisé (recommandé)

```bash
python scripts/mcp_smoke_test.py --base-url http://localhost:8081
# Avec auth:
python scripts/mcp_smoke_test.py \
  --base-url http://localhost:8081 \
  --auth-token "sk-obsirag-..."
```

### Test manuel SSE

Le transport actif est SSE avec un endpoint de session dynamique:

1. Ouvrir le flux: `GET /mcp/sse`
2. Lire l'événement `endpoint` qui contient `/mcp/messages/?session_id=...`
3. Envoyer les requêtes JSON-RPC en `POST` sur cet endpoint `messages`

#### 4.1 Ouvrir la session SSE

```bash
curl -N http://localhost:8081/mcp/sse
```

Réponse initiale attendue (exemple):

```text
event: endpoint
data: /mcp/messages/?session_id=abc123...
```

#### 4.2 Initialiser la session MCP

```bash
curl -X POST "http://localhost:8081/mcp/messages/?session_id=abc123..." \
  -H "Authorization: Bearer sk-obsirag-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "test-client", "version": "1.0"}
    }
  }'
```

Le serveur répond `202 Accepted`; la réponse JSON-RPC arrive ensuite sur le flux SSE.

Réponse JSON-RPC attendue sur le flux SSE:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {
      "name": "ObsiRAG",
      "version": "0.1.0"
    }
  }
}
```

#### 4.3 Lister les outils

```bash
curl -X POST "http://localhost:8081/mcp/messages/?session_id=abc123..." \
  -H "Authorization: Bearer sk-obsirag-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }'
```

#### 4.4 Appeler un outil (exemple: get_system_status)

```bash
curl -X POST "http://localhost:8081/mcp/messages/?session_id=abc123..." \
  -H "Authorization: Bearer sk-obsirag-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" \
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

## 5. Intégrer avec Claude Desktop

### Configuration

Fichier: `~/Library/Application\ Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "obsirag": {
      "url": "http://localhost:8081/mcp",
      "auth": {
        "type": "bearer",
        "token": "sk-obsirag-a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
      }
    }
  }
}
```

### Restart Claude Desktop

```bash
killall "Claude"
open -a Claude
```

Puis dans le chat Claude, vous pouvez utiliser les outils ObsiRAG comme n'importe quel MCP.

## 6. Dépannage

| Problème | Cause | Solution |
|----------|-------|----------|
| `401 Unauthorized` | Token manquant | Ajouter `-H "Authorization: Bearer ..."`  |
| `403 Forbidden` | Token invalide | Vérifier que `MCP_AUTH_TOKEN` en `.env` correspond |
| `Connection refused` | Service pas lancé | Exécuter `./start.sh` |
| `initialize` timeout (Claude) | Mauvais format requête | Vérifier `protocolVersion: "2024-11-05"` |
| Logs MCP non visibles | Logs en arrière-plan | `tail -f logs/obsirag.log \| grep MCP` |

## 7. Performance

- **Initialize:** ~50-100ms (vs 5-30s en stdio subprocess)
- **Tools:** ~200-500ms (backend + réseau)
- **Concurrence:** Illimitée (FastAPI)

## Voir aussi

- [MCP HTTP Documentation](./MCP_HTTP.md)
- [Architecture](./architecture.md)
