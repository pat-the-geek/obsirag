# Séquences ObsiRAG

Ce document décrit, sous forme de diagrammes de séquence simplifiés, les quatre flux principaux du système : démarrage, requête chat, cycle auto-apprenissage, et événement watcher. Il complète `architecture.md` en en détaillant les interactions runtime entre composants.

---

## 1. Démarrage de l'application

```mermaid
sequenceDiagram
    participant UI as UI Streamlit
    participant SC as ServiceCache<br/>(services_cache.py)
    participant SM as ServiceManager<br/>(services.py)
    participant CS as ChromaStore
    participant MLX as MLXClient
    participant RAG as RAGPipeline
    participant IDX as IndexingPipeline
    participant AL as AutoLearner
    participant VW as VaultWatcher

    UI->>SC: get_services()
    SC->>SM: ServiceManager(settings)
    activate SM
    SM->>CS: ChromaStore(settings)
    SM->>MLX: MLXClient(settings)
    SM->>RAG: RAGPipeline(chroma, llm)
    SM->>IDX: IndexingPipeline(chroma)
    SM->>AL: AutoLearner(settings, chroma, llm)
    SM->>VW: VaultWatcher(settings, on_change_fn)
    SM-->>SC: instance ServiceManager
    deactivate SM
    SC-->>UI: svc
    UI->>SM: svc.start()
    SM->>VW: start() [thread]
    SM->>IDX: run_initial_indexing() [thread]
    SM->>AL: start() [thread, si activé]
```

---

## 2. Requête chat (pipeline RAG complet)

```mermaid
sequenceDiagram
    participant U as Utilisateur
    participant APP as app.py
    participant RAG as RAGPipeline
    participant RS as RetrievalStrategy
    participant CS as ChromaStore
    participant AP as AnswerPrompting
    participant MLX as MLXClient

    U->>APP: saisie question
    APP->>RAG: stream_answer(question, history)
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
    MLX-->>APP: tokens (stream)
    deactivate RAG
    APP-->>U: réponse progressive
```

---

## 3. Cycle AutoLearner (traitement d'une note)

```mermaid
sequenceDiagram
    participant AL as AutoLearner
    participant ES as EntityServices
    participant EC as EntityCache<br/>(WuddaiCache/GeocodeCache)
    participant QA as QuestionAnswering
    participant WE as WebEnrichment
    participant MLX as MLXClient
    participant AW as ArtifactWriter
    participant CS as ChromaStore

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
