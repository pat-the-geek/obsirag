from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import app
from src.api.app import _build_conversation_theme_coverage_section
from src.api.app import _build_source_models
from src.api.app import _conversation_size_bytes
from src.api.app import _artifact_size_bytes
from src.api.app import _iter_answer_tokens
from src.api.app import _lookup_conversation_entity_contexts
from src.api.app import _normalize_indexing_status
from src.api.app import _normalize_report_markdown
from src.api.app import _related_note_from_note
from src.api.conversation_store import ApiConversationStore
from src.api.schemas import ChatMessageModel
from src.api.schemas import ConversationDetailModel


class _StubServiceManager:
    def __init__(self) -> None:
        self.llm = MagicMock()
        self.llm.is_available.return_value = True
        self.learner = MagicMock()
        self.indexer = MagicMock()
        self.learner.processing_status = {"active": False, "log": []}
        self.learner._scheduler = MagicMock()
        self.learner._scheduler.get_job.return_value = None
        self.indexing_status = {"running": False, "processed": 0, "total": 0, "current": ""}
        self.chroma = MagicMock()
        self.chroma.count_notes.return_value = 1
        self.chroma.count.return_value = 3
        self.chroma.list_notes_sorted_by_title.return_value = []
        self.chroma.list_notes.return_value = []
        self.chroma.list_note_folders.return_value = []
        self.chroma.list_note_tags.return_value = []
        self.chroma.invalidate_list_notes_cache.return_value = None
        self.rag = MagicMock()
        self.rag.query.return_value = (
            "Reponse synchrone",
            [
                {
                    "metadata": {"file_path": "Space/Artemis II.md", "note_title": "Artemis II", "is_primary": True},
                    "score": 0.91,
                }
            ],
        )
        self.rag.query_stream.side_effect = self._query_stream

    def signal_ui_active(self) -> None:
        return None

    def enter_stream(self) -> None:
        return None

    def exit_stream(self) -> None:
        return None

    def _query_stream(self, prompt: str, chat_history=None, progress_callback=None):
        if callable(progress_callback):
            progress_callback({"phase": "retrieval", "message": "Recherche dans le coffre"})
            progress_callback({"phase": "generation", "message": "Generation MLX"})
        return iter(["Bonjour ", "depuis ", "SSE"]), [
            {
                "metadata": {"file_path": "Space/Artemis II.md", "note_title": "Artemis II", "is_primary": True},
                "score": 0.93,
            }
        ]


def _message(payload: dict) -> ChatMessageModel:
    return ChatMessageModel.model_validate(payload)


def test_create_session_open_mode(tmp_settings):
    with patch("src.api.app.settings", tmp_settings):
        client = TestClient(app)
        response = client.post("/api/v1/session", json={"accessToken": ""})

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["requiresAuth"] is False
    assert payload["mode"] == "open"


def test_create_session_rejects_invalid_token(tmp_settings):
    secured_settings = tmp_settings.model_copy(update={"api_access_token": "secret-token"})
    with patch("src.api.app.settings", secured_settings):
        client = TestClient(app)
        response = client.post("/api/v1/session", json={"accessToken": "wrong-token"})

    assert response.status_code == 401


def test_health_reflects_vector_store_degradation(tmp_settings):
    service_manager = _StubServiceManager()
    service_manager.chroma.native_api_available.return_value = False

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.get_service_manager", return_value=service_manager),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["vectorStoreAvailable"] is False


def test_system_status_includes_startup_steps(tmp_settings):
    startup_payload = {
        "ready": False,
        "steps": [
            "📁 Initialisation des répertoires de données…",
            "🤖 Initialisation du client MLX (chargement differe)…",
        ],
        "current_step": "🤖 Initialisation du client MLX (chargement differe)…",
        "updated_at": "2026-04-18T10:00:00+00:00",
    }
    tmp_settings.startup_status_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_settings.startup_status_file.write_text(json.dumps(startup_payload), encoding="utf-8")

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.ensure_service_manager_started"),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["startup"]["ready"] is False
    assert payload["startup"]["steps"] == startup_payload["steps"]
    assert payload["startup"]["currentStep"] == startup_payload["current_step"]
    assert payload["runtime"]["llmProvider"] == "MLX"
    assert payload["runtime"]["llmModel"] == tmp_settings.mlx_chat_model
    assert payload["runtime"]["vectorStore"] == "LanceDB"


def test_system_status_infers_ready_startup_when_status_file_is_missing(tmp_settings):
    tmp_settings.data_dir.mkdir(parents=True, exist_ok=True)
    tmp_settings.index_state_file.write_text(json.dumps({"note.md": "2026-04-18T08:00:00"}), encoding="utf-8")
    service_status_file = tmp_settings.data_dir / "stats" / "service_manager_status.json"
    service_status_file.parent.mkdir(parents=True, exist_ok=True)
    service_status_file.write_text(
        json.dumps({"running": False, "processed": 784, "total": 784, "current": "Notes/Journal.md"}),
        encoding="utf-8",
    )

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.ensure_service_manager_started"),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/system/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["startup"]["ready"] is True
    assert payload["startup"]["currentStep"] == "Tous les services sont opérationnels"
    assert payload["startup"]["steps"][-1] == "Tous les services sont opérationnels"


def test_normalize_indexing_status_replaces_stale_current_when_not_running():
    normalized = _normalize_indexing_status({
        "running": False,
        "processed": 789,
        "total": 789,
        "current": "OK-ia.ch/Valeurs - Vision/OK-ia.ch — quelles valeurs pour moi.md",
    })

    assert normalized == {
        "running": False,
        "processed": 789,
        "total": 789,
        "current": "Indexation terminee",
    }


def test_conversation_size_bytes_returns_positive_value():
    conversation = ConversationDetailModel(
        id="conv-1",
        title="Conversation de test",
        updatedAt="2026-04-19T12:00:00Z",
        draft="",
        messages=[],
    )

    assert _conversation_size_bytes(conversation) > 0


def test_artifact_size_bytes_returns_file_size_for_existing_vault_file(tmp_settings):
    artifact_path = tmp_settings.vault / "obsirag" / "insights" / "demo.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("demo insight", encoding="utf-8")

    with patch("src.api.app.settings", tmp_settings):
        assert _artifact_size_bytes("obsirag/insights/demo.md") == len("demo insight".encode("utf-8"))


def test_get_note_resolves_short_slug_to_matching_file_path(tmp_settings):
    service_manager = _StubServiceManager()
    canonical_path = "Rapports-WUDD-ai/2026-04-11_les-dernieres-a_et-si-la-matiere-noire-n-etait-pas-nee-l.md"
    note_payload = {
        "file_path": canonical_path,
        "title": "Second Big Bang noir",
        "tags": ["Big-Bang-noir"],
        "wikilinks": [],
        "date_modified": "2026-04-11T09:35:59.334720",
    }
    service_manager.chroma.get_note_by_file_path.side_effect = lambda path: note_payload if path == canonical_path else None
    service_manager.chroma.list_notes.return_value = [note_payload]
    service_manager.chroma.get_backlinks.return_value = []

    note_path = tmp_settings.vault / canonical_path
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("# Second Big Bang noir\n", encoding="utf-8")

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.get_service_manager", return_value=service_manager),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/notes/2026-04-11_les-dernieres-a_et-si-la-matiere-noire-n-etait-pas-nee-l")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filePath"] == canonical_path
    assert payload["title"] == "Second Big Bang noir"


def test_related_note_from_note_includes_size_bytes(tmp_settings):
    note_path = tmp_settings.vault / "Space" / "Artemis II.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)
    note_path.write_text("Artemis II", encoding="utf-8")

    with patch("src.api.app.settings", tmp_settings):
        related = _related_note_from_note({
            "file_path": "Space/Artemis II.md",
            "title": "Artemis II",
            "date_modified": "2026-04-19T14:35:00Z",
        })

    assert related.sizeBytes == len("Artemis II".encode("utf-8"))


def test_delete_conversation_message_removes_target_message_and_previous_question(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    conversation = store.create("Test suppression")
    conversation.id = "conv-delete-message"
    conversation.messages = [
        _message({
            "id": "user-1",
            "role": "user",
            "content": "Question",
            "createdAt": "2026-04-17T12:00:00Z",
        }),
        _message({
            "id": "assistant-1",
            "role": "assistant",
            "content": "Premiere reponse",
            "createdAt": "2026-04-17T12:00:01Z",
            "stats": {"tokens": 10, "ttft": 0.3, "total": 1.0, "tps": 10.0},
        }),
        _message({
            "id": "user-2",
            "role": "user",
            "content": "Question suivante",
            "createdAt": "2026-04-17T12:00:02Z",
        }),
        _message({
            "id": "assistant-2",
            "role": "assistant",
            "content": "Seconde reponse",
            "createdAt": "2026-04-17T12:00:03Z",
            "stats": {"tokens": 20, "ttft": 0.4, "total": 2.0, "tps": 10.0},
        }),
    ]
    store.upsert(conversation)

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
    ):
        client = TestClient(app)
        response = client.delete("/api/v1/conversations/conv-delete-message/messages/assistant-2")

    assert response.status_code == 200
    payload = response.json()
    assert [message["id"] for message in payload["messages"]] == ["user-1", "assistant-1"]
    assert payload["lastGenerationStats"]["tokens"] == 10

    stored = store.get("conv-delete-message")
    assert stored is not None
    assert [message.id for message in stored.messages] == ["user-1", "assistant-1"]


def test_delete_conversation_message_returns_not_found_for_unknown_message(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    conversation = store.create("Test suppression")
    conversation.id = "conv-delete-missing"
    store.upsert(conversation)

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
    ):
        client = TestClient(app)
        response = client.delete("/api/v1/conversations/conv-delete-missing/messages/assistant-missing")

    assert response.status_code == 404


def test_get_conversation_removes_unanswered_trailing_question(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    conversation = store.create("Fil incomplet")
    conversation.id = "conv-repair-tail"
    conversation.messages = [
        _message({
            "id": "user-1",
            "role": "user",
            "content": "Question 1",
            "createdAt": "2026-04-17T12:00:00Z",
        }),
        _message({
            "id": "assistant-1",
            "role": "assistant",
            "content": "Reponse 1",
            "createdAt": "2026-04-17T12:00:01Z",
            "stats": {"tokens": 10, "ttft": 0.3, "total": 1.0, "tps": 10.0},
        }),
        _message({
            "id": "user-2",
            "role": "user",
            "content": "Question restee sans reponse",
            "createdAt": "2026-04-17T12:00:02Z",
        }),
    ]
    store.upsert(conversation)

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/conversations/conv-repair-tail")

    assert response.status_code == 200
    payload = response.json()
    assert [message["id"] for message in payload["messages"]] == ["user-1", "assistant-1"]
    assert payload["lastGenerationStats"]["tokens"] == 10

    stored = store.get("conv-repair-tail")
    assert stored is not None
    assert [message.id for message in stored.messages] == ["user-1", "assistant-1"]


def test_generate_conversation_report_creates_and_indexes_insight(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    source_note = tmp_settings.vault / "Space" / "Artemis II.md"
    source_note.parent.mkdir(parents=True, exist_ok=True)
    source_note.write_text(
        "# Artemis II\n\n![Capsule Orion](https://example.com/orion.png)\n",
        encoding="utf-8",
    )
    conversation = store.create("Mission Artemis")
    conversation.id = "conv-report"
    conversation.messages = [
        _message({
            "id": "user-1",
            "role": "user",
            "content": "Fais une synthese de la mission Artemis II.",
            "createdAt": "2026-04-18T12:00:00Z",
        }),
        _message({
            "id": "assistant-1",
            "role": "assistant",
            "content": "Artemis II valide Orion avant les prochaines missions lunaires.\n\n```mermaid\nflowchart TD\nA[Préparation] --> B[Vol circumlunaire]\n```",
            "createdAt": "2026-04-18T12:00:01Z",
            "sources": [
                {
                    "filePath": "Space/Artemis II.md",
                    "noteTitle": "Artemis II",
                }
            ],
            "entityContexts": [
                {
                    "type": "ORG",
                    "typeLabel": "Organisation",
                    "value": "NASA",
                    "imageUrl": "https://example.com/nasa.png",
                }
            ],
        }),
    ]
    store.upsert(conversation)


    service_manager = _StubServiceManager()
    service_manager.llm.chat.return_value = "# Rapport Artemis\n\n## Synthese\n\nMission de validation avant retour lunaire.\n"

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.conversation_store.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-report/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"].startswith("obsirag/insights/")
    saved_path = tmp_settings.vault / payload["path"]
    assert saved_path.exists()
    content = saved_path.read_text(encoding="utf-8")
    assert "type: rapport" in content
    assert "title: Rapport Mission Artemis" in content
    assert "## Corpus complet par themes" in content
    assert "#### Utilisateur" in content
    assert "Fais une synthese de la mission Artemis II." in content
    assert "#### Assistant" in content
    assert "Artemis II valide Orion avant les prochaines missions lunaires." in content
    assert "```mermaid" in content
    assert "A[Preparation] --> B[Vol circumlunaire]" in content
    assert "#### Illustrations associees" in content
    assert "![NASA](https://example.com/nasa.png)" in content
    assert "![Capsule Orion](https://example.com/orion.png)" in content
    service_manager.indexer.index_note.assert_called_once_with(saved_path)
    service_manager.chroma.invalidate_list_notes_cache.assert_called_once()


def test_normalize_report_markdown_deduplicates_ner_section_and_skips_placeholder_block():
    raw_markdown = """# Rapport Dune

### Entités NER - Index complet

- **Timothée Chalamet** (PERSON)
- **Dune** (WORK)
- **Dune Partie 3** (WORK)
- **Dune Troisième Partie Le Messie et son empire de sang** (WORK)
- **Dune 3 affiches sombres** (WORK)
- **Dune 3** (WORK)
- **IMAX 70mm** (MEDIUM)
- **Dune Partie Trois** (WORK)
- **Dune Partie 3** (WORK)
- **Warner Bros.** (ORG)

## Entites NER - Index complet

### PERSON
A completer.

### ORG
A completer.

### GPE
A completer.

### LOC
A completer.

### EVENT
A completer.

### SUBSTANCE
A completer.

### DATE
A completer.

*Sources :* Conversation uniquement
"""

    normalized = _normalize_report_markdown(
        raw_markdown,
        default_title="Rapport Dune",
        sources=[],
    )

    assert normalized.count("## Entites NER - Index complet") == 1
    assert normalized.count("- **Dune Partie 3** (WORK_OF_ART)") == 1
    assert "- **Dune Troisième Partie Le Messie et son empire de sang** (WORK_OF_ART)" not in normalized
    assert "- **Dune 3 affiches sombres** (WORK_OF_ART)" not in normalized
    assert "- **Dune 3** (WORK_OF_ART)" not in normalized
    assert "- **Dune Partie Trois** (WORK_OF_ART)" not in normalized
    assert "- **Dune Part Three** (WORK_OF_ART)" not in normalized
    assert "- **Dune Part Three Timothée Chalamet** (WORK_OF_ART)" not in normalized
    assert "### WORK_OF_ART" in normalized
    assert "### PERSON\n- **Timothée Chalamet** (PERSON)" in normalized
    assert "### ORG\n- **Warner Bros.** (ORG)" in normalized
    assert "### MEDIUM" in normalized
    assert "- **IMAX 70mm** (MEDIUM)" in normalized
    assert "A completer." not in normalized
    assert "### GPE" not in normalized
    assert "### DATE" not in normalized
    assert "### MISC" not in normalized


def test_normalize_report_markdown_extracts_embedded_markdown_document_before_ner_cleanup():
    raw_markdown = """# Rapport que sais-tu sur le film Dune ?

```markdown
---
title: Rapport que sais-tu sur le film Dune ?
date: 2026-04-15
type: rapport
statut: finalise
---

### Entités NER - Index complet

- **Timothée Chalamet** (PERSON)
- **Dune** (WORK_OF_ART)
- **Dune Partie 3** (WORK_OF_ART)
- **Dune Part Three** (WORK_OF_ART)
- **Dune 3 affiches sombres** (WORK_OF_ART)
- **IMAX 70mm** (MEDIUM)

## Entites NER - Index complet

### PERSON
A completer.

### ORG
A completer.

### GPE
A completer.

### LOC
A completer.

### EVENT
A completer.

### SUBSTANCE
A completer.

### DATE
A completer.
```
"""

    normalized = _normalize_report_markdown(
        raw_markdown,
        default_title="Rapport que sais-tu sur le film Dune ?",
        sources=[],
    )

    assert "```markdown" not in normalized
    assert normalized.count("## Entites NER - Index complet") == 1
    assert normalized.count("- **Dune Partie 3** (WORK_OF_ART)") == 1
    assert "- **Dune Part Three** (WORK_OF_ART)" not in normalized
    assert "- **Dune 3 affiches sombres** (WORK_OF_ART)" not in normalized
    assert "### MEDIUM" in normalized
    assert "A completer." not in normalized


def test_normalize_report_markdown_extracts_unclosed_embedded_markdown_document():
    raw_markdown = """# Rapport que sais-tu sur le film Dune ?

```markdown
---
title: Rapport que sais-tu sur le film Dune ?
date: 2026-04-15
type: rapport
statut: finalise
---

### Entités NER - Index complet

- **Timothée Chalamet** (PERSON)
- **Dune Partie 3** (WORK_OF_ART)
- **Dune Part Three** (WORK_OF_ART)
- **Dune 3 affiches sombres** (WORK_OF_ART)
- **IMAX 70mm** (MEDIUM)

## Entites NER - Index complet

### PERSON
A completer.

### ORG
A completer.
"""

    normalized = _normalize_report_markdown(
        raw_markdown,
        default_title="Rapport que sais-tu sur le film Dune ?",
        sources=[],
    )

    assert "```markdown" not in normalized
    assert normalized.count("## Entites NER - Index complet") == 1
    assert normalized.count("- **Dune Partie 3** (WORK_OF_ART)") == 1
    assert "- **Dune Part Three** (WORK_OF_ART)" not in normalized
    assert "- **Dune 3 affiches sombres** (WORK_OF_ART)" not in normalized
    assert "### MEDIUM" in normalized
    assert "A completer." not in normalized


def test_normalize_report_markdown_ignores_misc_noise_entries():
    raw_markdown = """# Rapport Dune

## Entites NER - Index complet

### MISC
- ****D** (MISC)
- **Denis Villeneuve** (PERSON)

*Sources :* Conversation uniquement
"""

    normalized = _normalize_report_markdown(
        raw_markdown,
        default_title="Rapport Dune",
        sources=[],
    )

    assert "### MISC" not in normalized
    assert "****D**" not in normalized
    assert "### PERSON" in normalized
    assert "- **Denis Villeneuve** (PERSON)" in normalized


def test_theme_coverage_section_keeps_readable_heading_without_midword_truncation():
    conversation = ConversationDetailModel.model_validate(
        {
            "id": "conv-theme-heading",
            "title": "Dune",
            "updatedAt": "2026-04-18T12:00:00Z",
            "draft": "",
            "messages": [
                {
                    "id": "user-1",
                    "role": "user",
                    "content": "ajoute à la conversation une synthèse de toutes les notes concernant les films Dune avec un focus sur les personnages, les maisons et les visions politiques décrites dans les sources",
                    "createdAt": "2026-04-18T12:00:00Z",
                },
                {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "Voici la synthèse regroupée.",
                    "createdAt": "2026-04-18T12:00:01Z",
                },
            ],
        }
    )

    section = _build_conversation_theme_coverage_section(conversation)
    heading_line = next(line for line in section.splitlines() if line.startswith("### Theme 1 - "))

    assert "ajoute à la conversation une synthèse de toutes les notes concernant les films Dune avec un focus sur les personnages" in heading_line
    assert "les maisons et les..." in heading_line
    assert not heading_line.endswith("avec u")
    assert not heading_line.endswith("avec u...")


def test_lookup_conversation_entity_contexts_requests_up_to_ten_entities():
    service_manager = _StubServiceManager()
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = []

    result = _lookup_conversation_entity_contexts("Parle-moi du MacBook Neo", "", service_manager)

    assert result == []
    service_manager.learner.lookup_wuddai_entity_contexts.assert_called_once_with(
        "Parle-moi du MacBook Neo",
        max_entities=10,
        max_notes=3,
    )


def test_stream_message_emits_sse_and_persists_messages(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    worker_payload = {
        "answer": "Bonjour depuis SSE",
        "sources": [
            {
                "metadata": {
                    "file_path": "Space/Artemis II.md",
                    "note_title": "Artemis II",
                    "is_primary": True,
                },
                "score": 0.93,
            }
        ],
    }

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(worker_payload, ensure_ascii=False),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-sse/messages/stream", json={"prompt": "Teste le streaming"})

    assert response.status_code == 200
    assert "event: message_start" in response.text
    assert "event: retrieval_status" in response.text
    assert "event: token" in response.text
    assert "event: message_complete" in response.text
    assert "Analyse de la requete" in response.text
    assert "Preparation du contexte" in response.text
    assert "Generation de la reponse" in response.text
    assert "Recherche DDG" not in response.text

    stored = store.get("conv-sse")
    assert stored is not None
    assert len(stored.messages) == 2
    assert stored.messages[0].role == "user"
    assert stored.messages[1].content == "Bonjour depuis SSE"
    assert stored.messages[1].timeline == [
        "Analyse de la requete",
        "Preparation du contexte",
        "Generation de la reponse",
        "Réponse générée par le worker API",
    ]


def test_iter_answer_tokens_preserves_mermaid_markdown_whitespace():
    answer = "### Diagramme\n\n```mermaid\nflowchart TD\n  A[Start] --> B[Done]\n```\n"

    tokens = _iter_answer_tokens(answer)

    assert "".join(tokens) == answer
    assert any("```mermaid\n" in token for token in tokens)
    assert any("B[Done]\n" in token for token in tokens)
    assert tokens[-1] == "```\n"


def test_build_source_models_deduplicates_duplicate_sources_and_promotes_primary(tmp_settings):
    sources = [
        {
            "metadata": {
                "file_path": "Space/Artemis II.md",
                "note_title": "Artemis II",
                "is_primary": False,
            },
            "score": 0.61,
        },
        {
            "metadata": {
                "file_path": "./Space/Artemis II.md",
                "note_title": " Artemis   II ",
                "is_primary": True,
            },
            "score": 0.93,
        },
        {
            "metadata": {
                "file_path": "Space/Orion.md",
                "note_title": "Orion",
                "is_primary": False,
            },
            "score": 0.52,
        },
    ]

    with patch("src.api.app.settings", tmp_settings):
        source_models = _build_source_models(sources)

    assert len(source_models) == 2
    assert [item.filePath for item in source_models] == ["Space/Artemis II.md", "Space/Orion.md"]
    assert source_models[0].isPrimary is True
    assert source_models[0].score == 0.93


def test_create_message_uses_fallback_worker_when_primary_worker_crashes(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    fallback_payload = {
        "answer": "Réponse via fallback lexical",
        "sources": [
            {
                "metadata": {
                    "file_path": "Space/Artemis II.md",
                    "note_title": "Artemis II",
                    "is_primary": True,
                },
                "score": 0.74,
            }
        ],
        "fallbackMode": "filesystem",
    }

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess(args=["python", "-m", "src.api.chat_worker"], returncode=139, stdout="", stderr=""),
                subprocess.CompletedProcess(
                    args=["python", "-m", "src.api.chat_fallback_worker"],
                    returncode=0,
                    stdout=(
                        "2026-04-17 12:00:00 | INFO | fallback worker ready\n"
                        + json.dumps(fallback_payload, ensure_ascii=False)
                        + "2026-04-17 12:00:01 | INFO | fallback worker done"
                    ),
                    stderr="",
                ),
            ],
        ) as run_mock,
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-fallback/messages", json={"prompt": "Parle-moi d'Artemis II"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == "Réponse via fallback lexical"
    assert payload["sources"][0]["filePath"] == "Space/Artemis II.md"
    assert run_mock.call_count == 2
    assert run_mock.call_args_list[0].args[0][2] == "src.api.chat_worker"
    assert run_mock.call_args_list[1].args[0][2] == "src.api.chat_fallback_worker"

    stored = store.get("conv-fallback")
    assert stored is not None
    assert len(stored.messages) == 2
    assert stored.messages[1].content == "Réponse via fallback lexical"


def test_create_message_deduplicates_duplicate_sources_in_response(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    worker_payload = {
        "answer": "Réponse avec sources dédupliquées",
        "sources": [
            {
                "metadata": {
                    "file_path": "Space/Artemis II.md",
                    "note_title": "Artemis II",
                    "is_primary": False,
                },
                "score": 0.74,
            },
            {
                "metadata": {
                    "file_path": "./Space/Artemis II.md",
                    "note_title": "Artemis II",
                    "is_primary": True,
                },
                "score": 0.91,
            },
            {
                "metadata": {
                    "file_path": "Space/Orion.md",
                    "note_title": "Orion",
                    "is_primary": False,
                },
                "score": 0.67,
            },
        ],
    }

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(worker_payload, ensure_ascii=False),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-source-dedupe/messages", json={"prompt": "Parle-moi d'Artemis II"})

    assert response.status_code == 200
    payload = response.json()
    assert [item["filePath"] for item in payload["sources"]] == ["Space/Artemis II.md", "Space/Orion.md"]
    assert payload["primarySource"]["filePath"] == "Space/Artemis II.md"

    stored = store.get("conv-source-dedupe")
    assert stored is not None
    assert [item.filePath for item in stored.messages[1].sources] == ["Space/Artemis II.md", "Space/Orion.md"]


def test_create_message_returns_legacy_style_enrichment_panels(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = [
        {
            "type": "person",
            "type_label": "Personne",
            "value": "Napoleon Bonaparte",
            "mentions": 4,
            "tag": "Napoleon",
            "notes": [
                {
                    "title": "Napoleon",
                    "file_path": "People/Napoleon.md",
                    "date_modified": "2026-04-16T09:00:00Z",
                }
            ],
            "ddg_knowledge": {
                "heading": "Napoleon Bonaparte",
                "abstract_text": "Empereur des Francais et figure militaire majeure.",
                "answer": "Empereur des Francais",
                "answer_type": "person",
                "definition": "Chef militaire et homme d Etat.",
                "infobox": [{"label": "Naissance", "value": "1769"}],
                "related_topics": [{"text": "Bataille de Waterloo", "url": "https://example.com/waterloo"}],
            },
        }
    ]

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.build_query_overview_sync",
            return_value={
                "query": "Napoleon",
                "search_query": "Napoleon biography overview",
                "summary": "Napoleon est une figure centrale de l'histoire francaise.",
                "sources": [{"title": "Wikipedia", "href": "https://example.com/napoleon", "body": "Biographie courte", "date": "2026-04-16"}],
            },
        ),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(
                    {
                        "answer": "Cette information n'est pas dans ton coffre.",
                        "sources": [
                            {
                                "metadata": {
                                    "file_path": "People/Napoleon.md",
                                    "note_title": "Napoleon",
                                    "is_primary": True,
                                },
                                "score": 0.91,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            ),
        ),
        patch("src.ai.web_search._ddg_search", return_value=[]),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-enriched/messages", json={"prompt": "Parle-moi de Napoleon"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["queryOverview"]["searchQuery"] == "Napoleon biography overview"
    assert payload["queryOverview"]["sources"][0]["href"] == "https://example.com/napoleon"
    assert payload["entityContexts"][0]["value"] == "Napoleon Bonaparte"
    assert payload["entityContexts"][0]["notes"][0]["filePath"] == "People/Napoleon.md"
    assert payload["entityContexts"][0]["ddgKnowledge"]["infobox"][0]["label"] == "Naissance"

    stored = store.get("conv-enriched")
    assert stored is not None
    assert stored.messages[1].queryOverview is not None
    assert stored.messages[1].entityContexts[0].value == "Napoleon Bonaparte"


def test_create_message_keeps_ner_without_ddg_for_vault_answer(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = [
        {
            "type": "concept",
            "type_label": "Concept",
            "value": "Artemis Program",
            "mentions": 2,
            "notes": [],
        }
    ]

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch("src.api.app.build_query_overview_sync") as overview_mock,
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(
                    {
                        "answer": "Artemis Program est bien documente dans le coffre.",
                        "sources": [
                            {
                                "metadata": {
                                    "file_path": "Space/Artemis Program.md",
                                    "note_title": "Artemis Program",
                                    "is_primary": True,
                                },
                                "score": 0.87,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-vault-answer/messages", json={"prompt": "Que sais-tu sur Artemis Program ?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["queryOverview"] is None
    assert payload["entityContexts"][0]["value"] == "Artemis Program"
    overview_mock.assert_not_called()


def test_create_message_uses_autolearn_hybrid_answer_when_vault_response_is_weak(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    worker_sources = [
        {
            "metadata": {
                "file_path": "People/Ada.md",
                "note_title": "Ada",
                "is_primary": True,
            },
            "score": 0.87,
        }
    ]
    service_manager.learner._is_weak_answer.side_effect = [True, False]
    service_manager.learner._web_search.return_value = [
        {
            "title": "Britannica",
            "href": "https://example.com/ada",
            "body": "Ada Lovelace a publie des notes sur la machine analytique.",
            "full_text": "Ada Lovelace a publie en 1843 des notes sur la machine analytique de Babbage.",
            "date": "2026-04-16",
        }
    ]
    service_manager.learner._build_web_search_query.return_value = "Ada Lovelace explication analyse histoire contexte"
    service_manager.learner._snippets_relevant.return_value = True
    service_manager.learner._question_answering._build_rag_context.return_value = ("Contexte coffre Ada", worker_sources)
    service_manager.learner._question_answering._compose_web_answer.return_value = (
        "Ada Lovelace a documente la machine analytique avec un apport hybride coffre et web.",
        worker_sources,
        service_manager.learner._web_search.return_value,
        "Web + Coffre",
    )
    service_manager.learner._question_answering._is_grounded_web_answer.return_value = True

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.build_query_overview_from_results_sync",
            return_value={
                "query": "Ada Lovelace",
                "search_query": "Ada Lovelace explication analyse histoire contexte",
                "summary": "Vue hybride issue du pipeline autolearner.",
                "sources": [{"title": "Britannica", "href": "https://example.com/ada", "body": "Ada Lovelace", "date": "2026-04-16"}],
            },
        ),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(
                    {
                        "answer": "Je ne peux pas répondre de manière exhaustive à partir du coffre seul.",
                        "sources": worker_sources,
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-hybrid/messages", json={"prompt": "Ada Lovelace"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"].startswith("Ada Lovelace a documente")
    assert payload["provenance"] == "hybrid"
    assert payload["queryOverview"] is None
    assert payload["enrichmentPath"].startswith("autolearn-web:")

    stored = store.get("conv-hybrid")
    assert stored is not None
    assert stored.messages[1].provenance == "hybrid"
    assert stored.messages[1].queryOverview is None


def test_stream_message_emits_legacy_style_enrichment_panels(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = [
        {
            "type": "concept",
            "type_label": "Concept",
            "value": "Artemis Program",
            "mentions": 2,
            "notes": [],
            "ddg_knowledge": {
                "heading": "Artemis Program",
                "abstract_text": "Programme d'exploration lunaire de la NASA.",
            },
        }
    ]
    worker_payload = {
        "answer": "Artemis Program structure la mission lunaire.",
        "sources": [
            {
                "metadata": {
                    "file_path": "Space/Artemis Program.md",
                    "note_title": "Artemis Program",
                    "is_primary": True,
                },
                "score": 0.88,
            }
        ],
    }

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.build_query_overview_sync",
            return_value={
                "query": "Artemis Program",
                "search_query": "Artemis Program NASA moon mission",
                "summary": "Artemis Program designe le programme lunaire de la NASA.",
                "sources": [{"title": "NASA", "href": "https://example.com/artemis", "body": "Vue d'ensemble", "date": "2026-04-16"}],
            },
        ),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(worker_payload, ensure_ascii=False),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-stream-enriched/messages/stream", json={"prompt": "Que sais-tu sur Artemis Program ?"})

    assert response.status_code == 200
    assert 'Recherche DDG' not in response.text

    stored = store.get("conv-stream-enriched")
    assert stored is not None
    assert stored.messages[1].queryOverview is None


def test_stream_message_uses_autolearn_hybrid_answer_when_web_enrichment_is_needed(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    worker_sources = [
        {
            "metadata": {
                "file_path": "People/Ada.md",
                "note_title": "Ada",
                "is_primary": True,
            },
            "score": 0.87,
        }
    ]
    service_manager.learner._web_search.return_value = [
        {
            "title": "Britannica",
            "href": "https://example.com/ada",
            "body": "Ada Lovelace mathematician.",
            "full_text": "Ada Lovelace published analytical engine notes in 1843.",
            "date": "2026-04-16",
        }
    ]
    service_manager.learner._build_web_search_query.return_value = "Ada Lovelace explication analyse histoire contexte"
    service_manager.learner._snippets_relevant.return_value = True
    service_manager.learner._is_weak_answer.side_effect = [True, False]
    service_manager.learner._question_answering._build_rag_context.return_value = ("Contexte coffre Ada", worker_sources)
    service_manager.learner._question_answering._compose_web_answer.return_value = (
        "Ada Lovelace a lie le coffre et le web dans cette reponse enrichie.",
        worker_sources,
        service_manager.learner._web_search.return_value,
        "Web + Coffre",
    )
    service_manager.learner._question_answering._is_grounded_web_answer.return_value = True

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.build_query_overview_from_results_sync",
            return_value={
                "query": "Ada Lovelace",
                "search_query": "Ada Lovelace explication analyse histoire contexte",
                "summary": "Vue hybride issue du pipeline autolearner.",
                "sources": [{"title": "Britannica", "href": "https://example.com/ada", "body": "Ada Lovelace", "date": "2026-04-16"}],
            },
        ),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(
                    {
                        "answer": "Je ne peux pas répondre de manière exhaustive à partir du coffre seul.",
                        "sources": worker_sources,
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-stream-hybrid/messages/stream", json={"prompt": "Ada Lovelace"})

    assert response.status_code == 200
    assert response.text.find("Je ne peux pas répondre de manière exhaustive") < response.text.find("Recherche DDG")
    assert "Recherche DDG" in response.text
    assert "Ada Lovelace a lie le coffre et le web" in response.text

    stored = store.get("conv-stream-hybrid")
    assert stored is not None
    assert stored.messages[1].provenance == "hybrid"
    assert stored.messages[1].queryOverview is None


def test_conversation_store_clears_legacy_hybrid_query_overview_on_read(tmp_path: Path, tmp_settings):
    store_path = tmp_path / "api" / "conversations.json"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(
            {
                "conversations": [
                    {
                        "id": "legacy-hybrid",
                        "title": "Legacy hybrid",
                        "updatedAt": "2026-04-19T14:00:00+00:00",
                        "draft": "",
                        "messages": [
                            {
                                "id": "user-1",
                                "role": "user",
                                "content": "Qui a fait le premier pas sur la lune ?",
                                "createdAt": "2026-04-19T13:49:36+00:00",
                                "sources": [],
                                "primarySource": None,
                                "stats": None,
                                "timeline": [],
                                "queryOverview": None,
                                "entityContexts": [],
                                "enrichmentPath": None,
                                "provenance": "unknown",
                                "sentinel": False,
                            },
                            {
                                "id": "assistant-1",
                                "role": "assistant",
                                "content": "Neil Armstrong a effectue le premier pas sur la Lune.",
                                "createdAt": "2026-04-19T13:51:23+00:00",
                                "sources": [],
                                "primarySource": None,
                                "stats": None,
                                "timeline": [],
                                "queryOverview": {
                                    "query": "Qui a fait le premier pas sur la lune ?",
                                    "searchQuery": "Qui a fait le premier pas sur la lune ? explication analyse histoire contexte",
                                    "summary": "Neil Armstrong a effectue le premier pas sur la Lune lors d'Apollo 11.",
                                    "sources": [],
                                },
                                "entityContexts": [],
                                "enrichmentPath": "autolearn-web:moon-step",
                                "provenance": "hybrid",
                                "sentinel": False,
                            },
                            {
                                "id": "assistant-2",
                                "role": "assistant",
                                "content": "Les notes mentionnent Artemis III et Artemis IV, sans details supplementaires.",
                                "createdAt": "2026-04-19T14:01:23+00:00",
                                "sources": [],
                                "primarySource": None,
                                "stats": None,
                                "timeline": [],
                                "queryOverview": {
                                    "query": "Parle moi de Artemis 3 et 4",
                                    "searchQuery": "Parle moi de Artemis 3 et 4 explication analyse histoire contexte",
                                    "summary": "Vue d'ensemble obsolète en double.",
                                    "sources": [],
                                },
                                "entityContexts": [],
                                "enrichmentPath": None,
                                "provenance": "vault",
                                "sentinel": False,
                            },
                        ],
                        "lastGenerationStats": None,
                    }
                ],
                "updatedAt": "2026-04-19T14:00:00+00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    store = ApiConversationStore(store_path)
    conversation = store.get("legacy-hybrid")

    assert conversation is not None
    assert conversation.messages[1].provenance == "hybrid"
    assert conversation.messages[1].queryOverview is None
    assert conversation.messages[2].provenance == "vault"
    assert conversation.messages[2].queryOverview is None


def test_graph_subgraph_returns_focused_neighbors(tmp_settings):
    service_manager = _StubServiceManager()
    notes = [
        {
            "file_path": "Space/Artemis II.md",
            "title": "Artemis II",
            "wikilinks": ["Artemis Program"],
            "tags": ["space"],
            "date_modified": "2026-04-16T09:00:00Z",
        },
        {
            "file_path": "Space/Artemis Program.md",
            "title": "Artemis Program",
            "wikilinks": [],
            "tags": ["space"],
            "date_modified": "2026-04-15T09:00:00Z",
        },
        {
            "file_path": "Science/Other.md",
            "title": "Other",
            "wikilinks": [],
            "tags": [],
            "date_modified": "2026-03-20T09:00:00Z",
        },
    ]
    service_manager.chroma.list_notes.return_value = notes
    service_manager.chroma.list_notes_sorted_by_title.return_value = notes
    service_manager.chroma.list_note_folders.return_value = ["Science", "Space"]
    service_manager.chroma.list_note_tags.return_value = ["space"]

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.get_service_manager", return_value=service_manager),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/graph/subgraph", params={"noteId": "Space/Artemis II.md", "depth": 1})

    assert response.status_code == 200
    payload = response.json()
    node_ids = {node["id"] for node in payload["nodes"]}
    assert "Space/Artemis II.md" in node_ids
    assert "Space/Artemis Program.md" in node_ids
    assert "Science/Other.md" not in node_ids
    focused = next(node for node in payload["nodes"] if node["id"] == "Space/Artemis II.md")
    assert focused["noteType"] == "user"
    assert focused["dateModified"] == "2026-04-16T09:00:00Z"
    assert payload["metrics"]["filteredNoteCount"] == 2
    assert payload["metrics"]["totalNoteCount"] == 3
    assert payload["filterOptions"]["folders"] == ["Science", "Space"]


def test_graph_returns_legacy_style_complete_payload(tmp_settings):
    service_manager = _StubServiceManager()
    notes = [
        {
            "file_path": "Space/Artemis II.md",
            "title": "Artemis II",
            "wikilinks": ["Artemis Program"],
            "tags": ["mission", "nasa"],
            "date_modified": "2026-04-16T09:00:00Z",
        },
        {
            "file_path": "obsirag/insights/Artemis Program.md",
            "title": "Artemis Program",
            "wikilinks": [],
            "tags": ["program", "nasa"],
            "date_modified": "2026-04-15T09:00:00Z",
        },
        {
            "file_path": "Science/Other.md",
            "title": "Other",
            "wikilinks": [],
            "tags": ["archive"],
            "date_modified": "2026-03-20T09:00:00Z",
        },
    ]
    service_manager.chroma.list_notes_sorted_by_title.return_value = notes
    service_manager.chroma.list_note_folders.return_value = ["Science", "Space", "obsirag/insights"]
    service_manager.chroma.list_note_tags.return_value = ["archive", "mission", "nasa", "program"]

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.get_service_manager", return_value=service_manager),
    ):
        client = TestClient(app)
        response = client.get("/api/v1/graph", params={"noteTypes": "insight", "searchText": "Artemis"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["filteredNoteCount"] == 1
    assert payload["metrics"]["totalNoteCount"] == 3
    assert payload["filterOptions"]["types"] == ["user", "report", "insight", "synapse"]
    assert payload["legend"][0]["label"] == "Note"
    assert payload["noteOptions"][0]["title"] == "Artemis II"
    assert payload["spotlight"][0]["filePath"] == "obsirag/insights/Artemis Program.md"
    assert payload["recentNotes"][0]["filePath"] == "obsirag/insights/Artemis Program.md"
    assert payload["typeSummary"][0]["label"] == "insight"


def test_explicit_web_search_returns_overview_and_entity_contexts(tmp_settings):
    service_manager = _StubServiceManager()
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = [
        {
            "type": "person",
            "type_label": "Personne",
            "value": "Ada Lovelace",
            "mentions": 1,
            "notes": [],
        }
    ]

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.build_query_overview_sync",
            return_value={
                "query": "Ada Lovelace",
                "search_query": "Ada Lovelace biography overview",
                "summary": "Ada Lovelace est une pionniere de l'informatique.",
                "sources": [{"title": "Wikipedia", "href": "https://example.com", "body": "Ada Lovelace", "date": "2026-04-16"}],
            },
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/web-search", json={"query": "Ada Lovelace"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provenance"] == "web"
    assert payload["queryOverview"]["query"] == "Ada Lovelace"
    assert payload["queryOverview"]["sources"][0]["href"] == "https://example.com"
    assert payload["queryOverview"]["sources"][0]["domain"] == "example.com"
    assert payload["queryOverview"]["sources"][0]["publishedAt"] == "2026-04-16"
    assert payload["entityContexts"][0]["value"] == "Ada Lovelace"
    assert payload["stats"]["tokens"] > 0
    assert payload["stats"]["tps"] >= 0


def test_explicit_web_search_prefers_autolearn_web_pipeline_when_available(tmp_settings):
    service_manager = _StubServiceManager()
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = []
    service_manager.learner._web_search.return_value = [
        {
            "title": "Britannica",
            "href": "https://example.com/ada",
            "body": "Ada Lovelace mathematician.",
            "full_text": "Ada Lovelace full text from a trusted source.",
            "date": "2026-04-16",
        }
    ]
    service_manager.learner._build_web_search_query.return_value = "Ada Lovelace explication analyse histoire contexte"

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.build_query_overview_from_results_sync",
            return_value={
                "query": "Ada Lovelace",
                "search_query": "Ada Lovelace explication analyse histoire contexte",
                "summary": "Vue issue du pipeline autolearner.",
                "sources": [{"title": "Britannica", "href": "https://example.com/ada", "body": "Ada Lovelace mathematician.", "date": "2026-04-16"}],
            },
        ) as autolearn_overview_mock,
        patch("src.api.app.build_query_overview_sync") as ddg_overview_mock,
    ):
        client = TestClient(app)
        response = client.post("/api/v1/web-search", json={"query": "Ada Lovelace"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["queryOverview"]["summary"] == "Vue issue du pipeline autolearner."
    autolearn_overview_mock.assert_called_once()
    ddg_overview_mock.assert_not_called()


def test_lookup_query_overview_falls_back_to_ddg_when_autolearn_returns_non_list(tmp_settings):
    service_manager = _StubServiceManager()
    service_manager.learner._web_search.return_value = MagicMock()

    with (
        patch("src.api.app.build_query_overview_sync", return_value={"summary": "fallback"}) as overview_mock,
    ):
        result = __import__("src.api.app", fromlist=["_lookup_query_overview"])._lookup_query_overview("Ada Lovelace", service_manager)

    assert result == {"summary": "fallback"}
    overview_mock.assert_called_once_with("Ada Lovelace", service_manager.llm)


def test_create_message_enriches_entity_contexts_with_line_number_and_relation_explanation(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()
    source_note = tmp_settings.vault / "Space" / "Alpha Impulsion.md"
    source_note.parent.mkdir(parents=True, exist_ok=True)
    source_note.write_text(
        "---\n"
        "title: Alpha Impulsion\n"
        "---\n"
        "# Alpha Impulsion\n\n"
        "Alpha Impulsion développe des projets spatiaux ambitieux.\n"
        "Alphabet s'intéresse également aux mêmes projets de propulsion et d'observation orbitale.\n",
        encoding="utf-8",
    )
    service_manager.learner.lookup_wuddai_entity_contexts.return_value = [
        {
            "type": "ORG",
            "type_label": "Organisation",
            "value": "Alphabet",
            "mentions": 19,
            "notes": [
                {
                    "title": "Alpha Impulsion",
                    "file_path": "Space/Alpha Impulsion.md",
                }
            ],
        }
    ]
    service_manager.llm.chat.return_value = json.dumps(
        {
            "items": [
                {
                    "entity": "Alphabet",
                    "reason": "Alphabet est cité dans la source car elle suit aussi les projets spatiaux associés à Alpha Impulsion.",
                }
            ]
        },
        ensure_ascii=False,
    )

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
        patch(
            "src.api.app.subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=["python", "-m", "src.api.chat_worker"],
                returncode=0,
                stdout=json.dumps(
                    {
                        "answer": "Alpha Impulsion est présente dans le coffre avec plusieurs liens sectoriels.",
                        "sources": [
                            {
                                "metadata": {
                                    "file_path": "Space/Alpha Impulsion.md",
                                    "note_title": "Alpha Impulsion",
                                    "is_primary": True,
                                },
                                "score": 0.95,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                stderr="",
            ),
        ),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-entity-enriched/messages", json={"prompt": "Parle-moi de Alpha Impulsion"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["entityContexts"][0]["value"] == "Alphabet"
    assert payload["entityContexts"][0]["lineNumber"] == 7
    assert payload["entityContexts"][0]["relationExplanation"] == (
        "Alphabet est cité dans la source car elle suit aussi les projets spatiaux associés à Alpha Impulsion."
    )