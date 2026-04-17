from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.app import app
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


def test_stream_message_emits_sse_and_persists_messages(tmp_path: Path, tmp_settings):
    store = ApiConversationStore(tmp_path / "api" / "conversations.json")
    service_manager = _StubServiceManager()

    with (
        patch("src.api.app.settings", tmp_settings),
        patch("src.api.app.conversation_store", store),
        patch("src.api.app.get_service_manager", return_value=service_manager),
    ):
        client = TestClient(app)
        response = client.post("/api/v1/conversations/conv-sse/messages/stream", json={"prompt": "Teste le streaming"})

    assert response.status_code == 200
    assert "event: message_start" in response.text
    assert "event: retrieval_status" in response.text
    assert "event: token" in response.text
    assert "event: message_complete" in response.text

    stored = store.get("conv-sse")
    assert stored is not None
    assert len(stored.messages) == 2
    assert stored.messages[0].role == "user"
    assert stored.messages[1].content == "Bonjour depuis SSE"


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


def test_explicit_web_search_returns_overview(tmp_settings):
    service_manager = _StubServiceManager()

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