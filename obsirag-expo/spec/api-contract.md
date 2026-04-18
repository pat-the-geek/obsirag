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

## Session et conversations

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

Retour : `{ path }`.

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

Le payload final `message_complete` doit permettre de reconstruire un `ChatMessage` complet cote client, y compris les enrichissements NER et web. Exemple :

```json
{
  "id": "msg_01",
  "role": "assistant",
  "content": "Artemis II est une mission habitee du programme Artemis.",
  "createdAt": "2026-04-18T09:12:00Z",
  "sources": [
    {
      "filePath": "space/artemis.md",
      "noteTitle": "Programme Artemis",
      "score": 0.91,
      "isPrimary": true
    }
  ],
  "primarySource": {
    "filePath": "space/artemis.md",
    "noteTitle": "Programme Artemis",
    "score": 0.91,
    "isPrimary": true
  },
  "timeline": ["retrieval", "generation", "entity-enrichment"],
  "queryOverview": {
    "query": "Artemis II",
    "searchQuery": "Artemis II NASA crewed mission",
    "summary": "Mission habitee de test autour de la Lune.",
    "sources": []
  },
  "entityContexts": [
    {
      "type": "mission",
      "typeLabel": "Mission",
      "value": "Artemis II",
      "mentions": 2,
      "lineNumber": 18,
      "relationExplanation": "Cette mission est le sujet principal de la reponse.",
      "imageUrl": "https://.../artemis-ii.jpg",
      "notes": [
        {
          "title": "Programme Artemis",
          "filePath": "space/artemis.md",
          "dateModified": "2026-04-17T19:42:00Z"
        }
      ],
      "ddgKnowledge": {
        "heading": "Artemis 2",
        "entity": "space mission",
        "abstractText": "First crewed Artemis mission.",
        "infobox": [],
        "relatedTopics": []
      }
    }
  ],
  "enrichmentPath": "vault+entities",
  "provenance": "vault",
  "sentinel": false
}
```

Contraintes d'interpretation cote Expo :

- `entityContexts` peut etre vide meme si la reponse est valide,
- `lineNumber` et `relationExplanation` sont optionnels mais doivent etre preserves s'ils sont fournis,
- `ddgKnowledge` peut completer une entite issue du coffre sans changer la `provenance` globale,
- la UI ne deduit pas elle-meme le type ou les notes liees: elle affiche ce que l'API retourne.

## Evenements SSE recommandes

```text
message_start
retrieval_status
token
sources_ready
message_complete
message_error
```

## Modeles de reponse attendus

### ChatMessage

Le frontend Expo manipule une structure equivalente a :

```json
{
  "id": "msg_01",
  "role": "assistant",
  "content": "...",
  "createdAt": "2026-04-18T09:12:00Z",
  "sources": [],
  "primarySource": null,
  "stats": null,
  "timeline": [],
  "queryOverview": null,
  "entityContexts": [],
  "enrichmentPath": "vault+entities",
  "provenance": "vault",
  "sentinel": false
}
```

### EntityContext

Chaque entree de `entityContexts` peut contenir :

```json
{
  "type": "person",
  "typeLabel": "Personne",
  "value": "Ada Lovelace",
  "mentions": 1,
  "lineNumber": 42,
  "relationExplanation": "Personnalite citee comme exemple historique.",
  "imageUrl": "https://.../ada.jpg",
  "tag": "history",
  "notes": [
    {
      "title": "Ada Lovelace",
      "filePath": "people/ada-lovelace.md",
      "dateModified": "2026-04-10T08:00:00Z"
    }
  ],
  "ddgKnowledge": {
    "heading": "Ada Lovelace",
    "entity": "mathematician",
    "abstractText": "English mathematician and writer.",
    "answer": null,
    "answerType": null,
    "definition": null,
    "infobox": [],
    "relatedTopics": []
  }
}
```

## Notes

### GET /api/v1/notes/:id

Retour : `NoteDetail`.

## Exports de conversation

### POST /api/v1/conversations/:id/report

Genere un rapport markdown Obsidian a partir de la conversation, le sauvegarde dans `obsirag/insights/` et retourne `{ path }`.

### GET /api/v1/notes/search?q=

Recherche de notes pour navigation rapide.

## Insights

### GET /api/v1/insights

Retour : liste `InsightItem`.

### GET /api/v1/insights/:id

Retour : detail de l'artefact.

## Graph

### GET /api/v1/graph

Retour : `GraphData`.

### GET /api/v1/graph/subgraph?noteId=

Retour : sous-graphe centre sur une note.

## Web search explicite

### POST /api/v1/web-search

Body :

```json
{
  "query": "Qui est Ada Lovelace ?"
}
```

Retour : reponse enrichie web + `queryOverview` + `entityContexts` + provenance.

Exemple :

```json
{
  "content": "Ada Lovelace est une mathematicienne britannique du XIXe siecle.",
  "queryOverview": {
    "query": "Qui est Ada Lovelace ?",
    "searchQuery": "Ada Lovelace biography",
    "summary": "Pionniere de la programmation.",
    "sources": [
      {
        "title": "Ada Lovelace - Biography",
        "url": "https://example.com/ada",
        "snippet": "English mathematician and writer"
      }
    ]
  },
  "entityContexts": [
    {
      "type": "person",
      "typeLabel": "Personne",
      "value": "Ada Lovelace",
      "mentions": 1,
      "notes": [],
      "ddgKnowledge": {
        "heading": "Ada Lovelace",
        "entity": "mathematician",
        "abstractText": "English mathematician and writer.",
        "infobox": [],
        "relatedTopics": []
      }
    }
  ],
  "provenance": "web"
}
```
