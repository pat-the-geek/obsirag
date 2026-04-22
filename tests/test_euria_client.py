from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ai.euria_client import EuriaClient


def _response(payload: dict):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _stream_response(lines: list[str]):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.raise_for_status.return_value = None
    response.iter_lines.return_value = iter(lines)
    return response


def test_euria_client_retries_reasoning_only_truncated_response():
    truncated = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "content": None,
                    "reasoning": "Thinking Process... final answer would follow.",
                },
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 1700, "total_tokens": 1712},
    }
    completed = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": "OK",
                    "reasoning": "Thinking Process...",
                },
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 1800, "total_tokens": 1812},
    }

    with patch("src.ai.euria_client.requests.post", side_effect=[_response(truncated), _response(completed)]) as post:
        client = EuriaClient(url="https://example.invalid/chat", bearer="token")

        content = client.chat([{"role": "user", "content": "Réponds OK"}], max_tokens=1700)

    assert content == "OK"
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"]["max_tokens"] == 1700
    assert post.call_args_list[1].kwargs["json"]["max_tokens"] == 3400


def test_euria_client_raises_when_response_has_no_content_and_no_reasoning_retry_signal():
    empty = {
        "choices": [{"finish_reason": "stop", "message": {"content": None, "reasoning": None}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 0, "total_tokens": 10},
    }

    with patch("src.ai.euria_client.requests.post", return_value=_response(empty)):
        client = EuriaClient(url="https://example.invalid/chat", bearer="token")

        with pytest.raises(RuntimeError, match="aucun contenu exploitable"):
            client.chat([{"role": "user", "content": "Réponds OK"}])


def test_euria_client_stream_ignores_reasoning_chunks_and_yields_content_deltas():
    stream_lines = [
        'data: {"choices":[{"delta":{"role":"assistant","content":""},"finish_reason":null}]}',
        "",
        'data: {"choices":[{"delta":{"reasoning":"Thinking"},"finish_reason":null}]}',
        "",
        'data: {"choices":[{"delta":{"content":"Bon"},"finish_reason":null}]}',
        "",
        'data: {"choices":[{"delta":{"content":"jour"},"finish_reason":null}]}',
        "",
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "",
        'data: [DONE]',
    ]

    with patch("src.ai.euria_client.requests.post", return_value=_stream_response(stream_lines)) as post:
        client = EuriaClient(url="https://example.invalid/chat", bearer="token")

        tokens = list(
            client.stream(
                [{"role": "user", "content": "Réponds OK"}],
                operation="conversation_euria_fast_web",
                enable_web_search=True,
            )
        )

    assert tokens == ["Bon", "jour"]
    assert post.call_args.kwargs["json"]["stream"] is True
    assert post.call_args.kwargs["json"]["enable_web_search"] is True
    assert post.call_args.kwargs["stream"] is True


def test_euria_client_stream_retries_reasoning_only_truncated_stream():
    truncated_stream = [
        'data: {"choices":[{"delta":{"reasoning":"Thinking"},"finish_reason":null}]}',
        "",
        'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
        "",
        'data: [DONE]',
    ]
    completed_stream = [
        'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":null}]}',
        "",
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "",
        'data: [DONE]',
    ]

    with patch(
        "src.ai.euria_client.requests.post",
        side_effect=[_stream_response(truncated_stream), _stream_response(completed_stream)],
    ) as post:
        client = EuriaClient(url="https://example.invalid/chat", bearer="token")

        tokens = list(client.stream([{"role": "user", "content": "Réponds OK"}], max_tokens=1700))

    assert tokens == ["OK"]
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"]["max_tokens"] == 1700
    assert post.call_args_list[1].kwargs["json"]["max_tokens"] == 3400