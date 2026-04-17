# API Contract Summary

Ce document resume les endpoints que le frontend Expo attend du backend ObsiRAG.

## Health

### GET /api/v1/health

Retour minimal attendu :

```json
{
  "status": "ok",
  "version": "1.0.0",
  "llmAvailable": true,
  "vectorStoreAvailable": true
}
```

## System status

### GET /api/v1/system/status

Retour minimal attendu :

```json
{
  "backendReachable": true,
  "llmAvailable": true,
  "notesIndexed": 736,
  "chunksIndexed": 4812,
  "indexing": {
    "running": false,
    "processed": 736,
    "total": 736,
    "current": "Indexation terminee"
  },
  "autolearn": {
    "active": false,
    "step": "En attente",
    "log": ["Dernier cycle termine sans erreur"],
    "nextRunAt": "2026-04-16T19:00:00Z"
  },
  "alerts": []
}
```

## Conversations

## Session

### POST /api/v1/session

Valide un token optionnel et retourne l'etat de session.

Body :

```json
{
  "accessToken": "optionnel"
}
```

Retour :

```json
{
  "authenticated": true,
  "requiresAuth": false,
  "tokenPreview": null,
  "backendUrlHint": "http://localhost:8000",
  "mode": "open"
}
```

### GET /api/v1/session

Retourne la session courante a partir du header `Authorization: Bearer ...` si l'API est protegee.

### GET /api/v1/conversations

Retour : liste de `ConversationSummary`.

### POST /api/v1/conversations

Cree un nouveau fil.

### GET /api/v1/conversations/:id

Retour : `ConversationDetail`.

### DELETE /api/v1/conversations/:id

Supprime un fil.

### POST /api/v1/conversations/:id/save

Sauvegarde le fil courant dans le vault comme conversation markdown.

## Chat streaming

### POST /api/v1/conversations/:id/messages

Body :

```json
{
  "prompt": "Parle moi de Artemis II"
}
```

Reponse recommandee :

- soit un accusé de creation du tour + URL de stream SSE,
- soit un WebSocket deja etabli,
- soit une reponse non streamée fallback.

### POST /api/v1/conversations/:id/messages/stream

Flux `text/event-stream` utilise par le client Expo.

Evenements emis :

- `message_start`
- `retrieval_status`
- `token`
- `sources_ready`
- `message_complete`
- `message_error`

## Evenements SSE recommandes

```text
message_start
retrieval_status
token
sources_ready
message_complete
message_error
```

## Notes

### GET /api/v1/notes/:id

Retour : `NoteDetail`.

### GET /api/v1/notes/search?q=...

Recherche de notes pour navigation rapide.

## Insights

### GET /api/v1/insights

Retour : liste `InsightItem`.

### GET /api/v1/insights/:id

Retour : detail de l'artefact.

## Graph

### GET /api/v1/graph

Retour : `GraphData`.

### GET /api/v1/graph/subgraph?noteId=...

Retour : sous-graphe centre sur une note.

## Web search explicite

### POST /api/v1/web-search

Body :

```json
{
  "query": "Qui est Ada Lovelace ?"
}
```

Retour : reponse enrichie web + sources + provenance.
