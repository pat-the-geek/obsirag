from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.mcp.server import build_server, main


def test_build_server_registers_expected_tools() -> None:
    server = build_server()
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == {
        "obsirag_ask_rag",
        "obsirag_get_graph_subgraph",
        "obsirag_get_note",
        "obsirag_get_system_status",
        "obsirag_search_notes",
    }


def test_main_runs_stdio_transport() -> None:
    server = MagicMock()
    main_server = main.__globals__["build_server"]
    try:
        main.__globals__["build_server"] = lambda: server
        main()
    finally:
        main.__globals__["build_server"] = main_server

    server.run.assert_called_once_with(transport="stdio")
