from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.schemas import GraphDataModel, GraphFilterOptionsModel, GraphMetricsModel, NoteDetailModel, SourceRefModel
from src.mcp import runtime as mcp_runtime


def test_get_system_status_payload_serializes_model() -> None:
    expected = {
        "backendReachable": True,
        "llmAvailable": True,
        "notesIndexed": 1,
        "chunksIndexed": 2,
        "indexing": {"running": False, "processed": 1, "total": 1, "current": ""},
        "autolearn": {
            "active": False,
            "managedBy": "none",
            "running": False,
            "pid": None,
            "note": "",
            "step": "",
            "log": [],
            "startedAt": None,
            "updatedAt": None,
            "nextRunAt": None,
        },
        "startup": {"ready": True, "steps": [], "currentStep": "", "error": None, "updatedAt": None},
        "runtime": {
            "llmProvider": "Ollama",
            "llmModel": "qwen2.5:7b",
            "embeddingModel": "mini",
            "vectorStore": "ChromaDB",
            "nerModel": "xx_ent_wiki_sm",
            "autolearnMode": "disabled",
            "euriaProvider": None,
            "euriaModel": None,
            "euriaEnabled": False,
        },
        "alerts": [],
    }
    with patch("src.mcp.runtime.api_system_status") as api_system_status:
        api_system_status.return_value = MagicMock(model_dump=MagicMock(return_value=expected))
        assert mcp_runtime.get_system_status_payload() == expected


def test_search_notes_payload_applies_limit() -> None:
    notes = [
        MagicMock(model_dump=MagicMock(return_value={"title": "A", "filePath": "A.md"})),
        MagicMock(model_dump=MagicMock(return_value={"title": "B", "filePath": "B.md"})),
    ]
    with patch("src.mcp.runtime.api_search_notes", return_value=notes):
        payload = mcp_runtime.search_notes_payload("python", limit=1)
    assert payload == {
        "query": "python",
        "count": 1,
        "notes": [{"title": "A", "filePath": "A.md"}],
    }


def test_get_note_payload_converts_http_errors() -> None:
    with patch("src.mcp.runtime.api_get_note", side_effect=HTTPException(status_code=404, detail="Note not found")):
        with pytest.raises(ValueError, match="Note not found"):
            mcp_runtime.get_note_payload("missing.md")


def test_ask_rag_payload_formats_answer_and_sources() -> None:
    service_manager = MagicMock()
    service_manager.rag.query.return_value = (
        "Bonjour [Note Python]",
        [{"metadata": {"file_path": "Note Python.md", "note_title": "Note Python", "is_primary": True}, "score": 0.9}],
    )
    source_model = SourceRefModel(
        filePath="Note Python.md",
        noteTitle="Note Python",
        dateModified="2026-05-01T10:00:00",
        score=0.9,
        isPrimary=True,
    )
    with (
        patch("src.mcp.runtime.get_service_manager", return_value=service_manager),
        patch("src.mcp.runtime._build_source_models", return_value=[source_model]),
    ):
        payload = mcp_runtime.ask_rag_payload(
            "Que dit mon coffre ?",
            history=[{"role": "user", "content": "Parle-moi de Python"}],
        )

    service_manager.signal_ui_active.assert_called_once_with()
    service_manager.rag.query.assert_called_once_with(
        "Que dit mon coffre ?",
        chat_history=[{"role": "user", "content": "Parle-moi de Python"}],
        exclude_obsirag_generated=False,
    )
    assert payload["question"] == "Que dit mon coffre ?"
    assert payload["answer"] == "Bonjour [Note Python]"
    assert payload["sentinel"] is False
    assert payload["sourceCount"] == 1
    assert payload["primarySource"]["filePath"] == "Note Python.md"


def test_get_graph_subgraph_payload_serializes_model() -> None:
    graph_model = GraphDataModel(
        nodes=[],
        edges=[],
        metrics=GraphMetricsModel(nodeCount=1, edgeCount=0, density=0.0, filteredNoteCount=1, totalNoteCount=1),
        filterOptions=GraphFilterOptionsModel(),
    )
    with patch("src.mcp.runtime.api_get_graph_subgraph", return_value=graph_model) as api_get_graph_subgraph:
        payload = mcp_runtime.get_graph_subgraph_payload("Note Python.md", depth=2, tags=["python"])

    api_get_graph_subgraph.assert_called_once_with(
        noteId="Note Python.md",
        depth=2,
        folders=[],
        tags=["python"],
        noteTypes=[],
        searchText="",
        recencyDays=None,
    )
    assert payload["metrics"]["nodeCount"] == 1
