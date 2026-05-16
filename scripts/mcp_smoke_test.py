#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import threading
import time
from typing import Any

import requests

SESSION_PATH_RE = re.compile(r"/mcp/messages/\?session_id=[0-9a-f]+")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test MCP SSE transport (initialize + tools/list)."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8081",
        help="Base URL for ObsiRAG backend (default: http://localhost:8081)",
    )
    parser.add_argument(
        "--auth-token",
        default=os.getenv("MCP_AUTH_TOKEN", ""),
        help="Bearer token for MCP auth. Defaults to MCP_AUTH_TOKEN env var.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Timeout in seconds for handshake and MCP responses (default: 15)",
    )
    return parser.parse_args()


def _jsonrpc_init_payload() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "obsirag-mcp-smoke",
                "version": "1.0",
            },
        },
    }


def _jsonrpc_tools_list_payload() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    }


def main() -> int:
    args = _parse_args()
    base_url = args.base_url.rstrip("/")
    timeout = max(args.timeout, 1.0)

    headers: dict[str, str] = {}
    if args.auth_token:
        headers["Authorization"] = f"Bearer {args.auth_token}"

    queue_lines: queue.Queue[str] = queue.Queue()
    stop_reader = threading.Event()
    session = requests.Session()

    def _reader() -> None:
        try:
            with session.get(
                f"{base_url}/mcp/sse",
                headers=headers,
                stream=True,
                timeout=(5, timeout),
            ) as response:
                if response.status_code != 200:
                    queue_lines.put(f"__SSE_HTTP_ERROR__:{response.status_code}")
                    return
                queue_lines.put("__SSE_CONNECTED__")
                for raw in response.iter_lines(decode_unicode=True):
                    if stop_reader.is_set():
                        break
                    if raw is None:
                        continue
                    line = raw.strip()
                    if line:
                        queue_lines.put(line)
        except Exception as exc:  # pragma: no cover - smoke test guardrail
            queue_lines.put(f"__SSE_EXCEPTION__:{exc}")

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    print(f"[mcp-smoke] Connecting SSE: {base_url}/mcp/sse")
    sse_connected = False
    session_path = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = queue_lines.get(timeout=0.5)
        except queue.Empty:
            continue

        if line.startswith("__SSE_HTTP_ERROR__"):
            print(f"[mcp-smoke] FAIL: SSE returned {line.split(':', 1)[1]}")
            stop_reader.set()
            return 1
        if line.startswith("__SSE_EXCEPTION__"):
            print(f"[mcp-smoke] FAIL: SSE exception: {line.split(':', 1)[1]}")
            stop_reader.set()
            return 1
        if line == "__SSE_CONNECTED__":
            sse_connected = True
            continue

        if line.startswith("data: "):
            maybe_path = line[6:].strip()
            match = SESSION_PATH_RE.search(maybe_path)
            if match:
                session_path = match.group(0)
                break

    if not sse_connected:
        print("[mcp-smoke] FAIL: SSE not connected")
        stop_reader.set()
        return 1
    if not session_path:
        print("[mcp-smoke] FAIL: did not receive session endpoint from SSE stream")
        stop_reader.set()
        return 1

    print(f"[mcp-smoke] Session endpoint discovered: {session_path}")
    msg_url = f"{base_url}{session_path}"

    post_headers = {"Content-Type": "application/json", **headers}

    init_response = session.post(
        msg_url,
        headers=post_headers,
        json=_jsonrpc_init_payload(),
        timeout=timeout,
    )
    print(f"[mcp-smoke] POST initialize -> HTTP {init_response.status_code}")
    if init_response.status_code != 202:
        print(f"[mcp-smoke] FAIL: initialize not accepted: {init_response.text[:200]}")
        stop_reader.set()
        return 1

    list_response = session.post(
        msg_url,
        headers=post_headers,
        json=_jsonrpc_tools_list_payload(),
        timeout=timeout,
    )
    print(f"[mcp-smoke] POST tools/list -> HTTP {list_response.status_code}")
    if list_response.status_code != 202:
        print(f"[mcp-smoke] FAIL: tools/list not accepted: {list_response.text[:200]}")
        stop_reader.set()
        return 1

    init_ok = False
    tools_ok = False
    found_tools = 0
    deadline = time.time() + timeout
    while time.time() < deadline and (not init_ok or not tools_ok):
        try:
            line = queue_lines.get(timeout=0.5)
        except queue.Empty:
            continue

        if not line.startswith("data: "):
            continue

        payload = line[6:].strip()
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            continue

        msg_id = message.get("id")
        if msg_id == 1 and isinstance(message.get("result"), dict):
            init_ok = True
        if msg_id == 2 and isinstance(message.get("result"), dict):
            tools = message["result"].get("tools")
            if isinstance(tools, list):
                tools_ok = True
                found_tools = len(tools)

    stop_reader.set()
    session.close()

    if not init_ok:
        print("[mcp-smoke] FAIL: initialize result not received on SSE stream")
        return 1
    if not tools_ok:
        print("[mcp-smoke] FAIL: tools/list result not received on SSE stream")
        return 1

    print(f"[mcp-smoke] PASS: initialize + tools/list OK ({found_tools} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
