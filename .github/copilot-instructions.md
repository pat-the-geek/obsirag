# ObsiRAG Copilot instructions

## Build, test, and validation commands

Prefer the repository lifecycle scripts over launching pieces by hand:

```bash
./start.sh
./status.sh
./stop.sh
```

Backend validation and tests:

```bash
./scripts/validate_local.sh
./scripts/validate_local.sh --nrt
./scripts/validate_local.sh --full
./scripts/validate_local.sh --no-restart

source .venv/bin/activate
pytest
pytest --no-cov
pytest --no-cov tests/test_chat_ui_fragments.py
pytest --no-cov tests/test_rag.py -k dominant
```

Notes:

- `pytest` uses `pytest.ini` defaults with coverage on `src/` and `--cov-fail-under=90`.
- Use `--no-cov` for focused reruns, marker runs, and single-test debugging so coverage gates do not fail unrelated work.
- The ultra-short regression subset is marker-based: `pytest --no-cov -m nrt`.

Expo frontend commands:

```bash
cd obsirag-expo
npm run start
npm run web
npm run typecheck
npm run test:ui
npx jest --runInBand tests/ui/use-stream-message.test.tsx
npm run web:export
npm run test:web-export
```

## High-level architecture

ObsiRAG is a Python backend plus an Expo Router client:

- `src/api/main.py` exports the FastAPI app from `src/api/app.py`.
- `scripts/run_api.sh` runs `uvicorn src.api.main:app`.
- `start.sh` starts the FastAPI backend and then either:
  - serves `obsirag-expo/dist/` from the API when a static web export exists, or
  - launches Expo web in dev mode on port `8081`.

Runtime initialization is lazy and singleton-based:

- `src/api/runtime.py` owns the one-time startup path for `ServiceManager`.
- `src/services.py` wires together the vector store, LLM client, `RAGPipeline`, `IndexingPipeline`, `GraphBuilder`, `AutoLearner`, and `VaultWatcher`.
- Startup and runtime status are persisted under `data/stats/` through `JsonStateStore`.

The main product flow is:

1. Expo calls FastAPI endpoints for system status, conversations, notes, graph, and web search.
2. FastAPI persists conversation state through `ApiConversationStore` in `data/api/conversations.json`.
3. `RAGPipeline` handles retrieval, response shaping, dominant-note selection, sentinel handling, and response enrichment.
4. The API returns chat payloads that can include `sources`, `primarySource`, `queryOverview`, `entityContexts`, and explicit provenance for the Expo UI.
5. `IndexingPipeline` parses vault Markdown, chunks notes, and updates the configured vector store incrementally.
6. `AutoLearner` runs in the background and writes generated artifacts back into the vault plus JSON runtime state under `data/`.

The Streamlit UI under `src/ui/` is still in the repository, but the primary product runtime is FastAPI + Expo. Treat Streamlit as a legacy compatibility surface unless the task is explicitly about those pages.

## Key repository conventions

- Use the root scripts for runtime work. `start.sh`/`stop.sh`/`status.sh` are the expected entrypoints, and `validate_local.sh` is the standard post-change validation wrapper.
- Keep the FastAPI ↔ Expo response contract stable. The frontend already depends on fields like `primarySource`, `sources`, `entityContexts`, `queryOverview`, `provenance`, and streaming status events.
- Backend URL handling in Expo expects an origin only. Reuse `normalizeBackendUrlInput()` and do not store `/api/v1` paths in persisted server config.
- Backend state is deliberately file-backed. Conversations, startup status, metrics, query history, and other runtime state are stored through `JsonStateStore`; preserve those JSON persistence paths instead of introducing ad hoc formats.
- Generated markdown artifacts are part of the product surface. ObsiRAG writes insights/synthesis content into the vault and indexes those notes like the rest of the vault.
- Backend tests are designed around shared lightweight fixtures from `tests/conftest.py`. Prefer temp directories, mocks, and the existing pytest markers (`unit`, `integration`, `perf`, `smoke`, `nrt`, `live`) over real external services.
- When touching legacy Streamlit pages, prefer module imports over fragile named imports on hot-reload-sensitive UI modules, and keep reusable HTML/Mermaid rendering in the shared helper modules already used by the repo.
