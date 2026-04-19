# Séquences ObsiRAG

Ce document décrit, sous forme de diagrammes de séquence simplifiés, les quatre flux principaux du système : démarrage opérationnel, requête chat, cycle auto-apprenissage, et événement watcher. Il complète `architecture.md` en en détaillant les interactions runtime entre composants.

---

## 1. Démarrage opérationnel

```mermaid
sequenceDiagram
    participant DEV as Operateur
    participant START as start.sh
    participant LD as launchd<br/>(com.obsirag.autolearn)
    participant API as FastAPI / Uvicorn
    participant EXPO as Expo Web
    participant SM as ServiceManager<br/>(services.py)
    participant CS as ChromaStore
    participant MLX as MLXClient
    participant RAG as RAGPipeline
    participant IDX as IndexingPipeline
    participant AL as AutoLearner
    participant VW as VaultWatcher

    DEV->>START: ./start.sh
    START->>LD: verifier / charger worker autolearn
    START->>API: lancer scripts/run_api.sh
    API->>SM: ServiceManager(settings)
    activate SM
    SM->>CS: ChromaStore(settings)
    SM->>MLX: MLXClient(settings)
    SM->>RAG: RAGPipeline(chroma, llm)
    SM->>IDX: IndexingPipeline(chroma)
    SM->>AL: AutoLearner(chroma, rag, indexer, ...)
    SM->>VW: VaultWatcher(settings, on_change_fn)
    SM->>VW: start() [thread]
    SM->>IDX: run_initial_indexing() [thread]
    deactivate SM
    START->>EXPO: lancer scripts/run_expo_web.sh
    EXPO-->>DEV: UI web disponible sur :8081
    API-->>DEV: API disponible sur :8000
```

---

## 2. Requête chat (pipeline RAG complet)

```mermaid
sequenceDiagram
    participant U as Utilisateur
    participant EXPO as Client Expo
    participant API as app.py
    participant RAG as RAGPipeline
    participant RS as RetrievalStrategy
    participant CS as ChromaStore
    participant AP as AnswerPrompting
    participant MLX as MLXClient
    participant ES as EntityServices
    participant WS as WebSearch

    U->>EXPO: saisie question
    EXPO->>API: POST /api/v1/conversations/:id/messages/stream
    API->>RAG: stream_answer(question, history)
    activate RAG
    RAG->>RAG: resolve_question(question, history)
    RAG->>RS: retrieve(resolved_question)
    activate RS
    RS->>CS: search(query, k=…)
    CS-->>RS: chunks[]
    RS-->>RAG: chunks[]
    deactivate RS
    RAG->>AP: build_messages(question, chunks, history)
    AP->>CS: get_chunks_by_note_title / get_chunks_by_file_path
    CS-->>AP: linked_chunks[]
    AP-->>RAG: messages[]
    RAG->>MLX: stream(messages)
    MLX-->>API: tokens / answer
    API->>ES: lookup entity contexts(question, answer)
    ES-->>API: entityContexts[]
    opt information absente du coffre
        API->>WS: web_search(question)
        WS-->>API: queryOverview + sources web
    end
    deactivate RAG
    API-->>EXPO: SSE tokens + sources + note principale + provenance
    EXPO-->>U: réponse progressive
```

---

## 3. Cycle AutoLearner (worker persistant)

```mermaid
sequenceDiagram
    participant LD as launchd
    participant AL as AutoLearner
    participant ES as EntityServices
    participant EC as EntityCache<br/>(WuddaiCache/GeocodeCache)
    participant QA as QuestionAnswering
    participant WE as WebEnrichment
    participant MLX as MLXClient
    participant AW as ArtifactWriter
    participant CS as ChromaStore

    LD->>AL: run_autolearn_worker.sh
    AL->>AL: _select_notes_to_process()
    loop pour chaque note sélectionnée
        AL->>ES: extract_validated_entities(text)
        ES->>EC: WuddaiCache.load()
        EC-->>ES: entities[]
        ES-->>AL: tags, entity_images
        AL->>QA: generate_question(text)
        QA->>MLX: chat(prompt)
        MLX-->>QA: question
        QA-->>AL: question
        AL->>WE: fetch_web_context(question)
        WE-->>AL: web_results[]
        AL->>MLX: chat(synthesize_prompt)
        MLX-->>AL: insight_text
        AL->>AW: write_insight(note, insight_text, tags)
        AW-->>CS: upsert_chunk(insight)
        AL->>AL: _mark_processed(note)
    end
```

---

## 4. Événement VaultWatcher (modification d'une note)

```mermaid
sequenceDiagram
    participant FS as Filesystem
    participant VW as VaultWatcher
    participant IDX as IndexingPipeline
    participant CS as ChromaStore
    participant AL as AutoLearner

    FS->>VW: inotify/watchdog event (modify/create)
    VW->>VW: debounce (500 ms)
    VW->>IDX: index_note(file_path)
    activate IDX
    IDX->>IDX: parse + chunk note
    IDX->>CS: upsert_chunks(chunks)
    CS-->>IDX: ok
    deactivate IDX
    VW->>AL: notify_note_changed(file_path)
    Note over AL: marque la note comme non traitée<br/>pour le prochain cycle auto-apprenissage
```

---

## Note d'architecture

Les séquences ci-dessus décrivent le runtime principal actuel : `launchd` pour le worker auto-learner persistant, FastAPI pour le backend applicatif, et Expo web pour l'interface principale. Les flux historiques de l'ancienne UI ne sont plus la référence opératoire du produit.
