from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import app
from src.api.app import _lookup_conversation_entity_contexts
from src.api.conversation_store import ApiConversationStore


class _StubServiceManager:
    def __init__(self) -> None:
        self.llm = MagicMock()
        self.llm.is_available.return_value = True
        self.learner = MagicMock()
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


def test_delete_conversation_message_removes_target_message_and_previous_question(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    conversation = store.create("Test suppression")
    conversation.id = "conv-delete-message"
    conversation.messages = [
        {
            "id": "user-1",
            "role": "user",
            "content": "Question",
            "createdAt": "2026-04-17T12:00:00Z",
        },
        {
            "id": "assistant-1",
            "role": "assistant",
            "content": "Premiere reponse",
            "createdAt": "2026-04-17T12:00:01Z",
            "stats": {"tokens": 10, "ttft": 0.3, "total": 1.0, "tps": 10.0},
        },
        {
            "id": "user-2",
            "role": "user",
            "content": "Question suivante",
            "createdAt": "2026-04-17T12:00:02Z",
        },
        {
            "id": "assistant-2",
            "role": "assistant",
            "content": "Seconde reponse",
            "createdAt": "2026-04-17T12:00:03Z",
            "stats": {"tokens": 20, "ttft": 0.4, "total": 2.0, "tps": 10.0},
        },
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
    assert "Extraction des entites NER" in response.text
    assert "Finalisation de la reponse" in response.text
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
        "Extraction des entites NER",
        "Finalisation de la reponse",
    ]


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


def test_create_message_returns_streamlit_style_enrichment_panels(tmp_path: Path, tmp_settings):
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


def test_stream_message_emits_streamlit_style_enrichment_panels(tmp_path: Path, tmp_settings):
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
    assert '"entityContexts": [{' in response.text
    assert 'Extraction des entites NER' in response.text
    assert 'Recherche DDG' not in response.text

    stored = store.get("conv-stream-enriched")
    assert stored is not None
    assert stored.messages[1].queryOverview is None
    assert stored.messages[1].entityContexts[0].value == "Artemis Program"
    assert stored.messages[1].timeline[-2:] == [
        "Extraction des entites NER",
        "Finalisation de la reponse",
    ]


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


def test_graph_returns_streamlit_style_complete_payload(tmp_settings):
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