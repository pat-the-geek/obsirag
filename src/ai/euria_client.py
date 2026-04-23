from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import requests
from loguru import logger

from src.config import settings


class EuriaClient:
    DEFAULT_MODEL = "Qwen/Qwen3.5-122B-A10B-FP8"
    _RETRY_MAX_TOKENS = 4096
    _WEB_SEARCH_MAX_TOKENS = 12000

    def __init__(
        self,
        *,
        url: str | None = None,
        bearer: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._url = (url or settings.euria_url or "").strip()
        self._bearer = (bearer or settings.euria_bearer or "").strip()
        self._model = model
        if not self._url or not self._bearer:
            raise ValueError("URL et bearer Euria sont requis pour la conversation.")

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def is_loaded(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._url and self._bearer)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "chat",
        enable_web_search: bool | None = None,
    ) -> str:
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_web_search=enable_web_search,
        )

        data = self._post_chat(payload)
        content = self._extract_message_content(data)
        if not content and self._should_retry_for_reasoning_only(data, max_tokens):
            is_web_search = bool(payload.get("enable_web_search"))
            retry_ceil = self._WEB_SEARCH_MAX_TOKENS if is_web_search else self._RETRY_MAX_TOKENS
            retry_payload = dict(payload)
            retry_payload["max_tokens"] = min(retry_ceil, max(max_tokens * 4 if is_web_search else max_tokens * 2, 8000 if is_web_search else 2200))
            logger.info(
                "[EuriaClient] {} retrying truncated reasoning-only response with max_tokens={} (web_search={})",
                operation,
                retry_payload["max_tokens"],
                is_web_search,
            )
            data = self._post_chat(retry_payload)
            content = self._extract_message_content(data)

        if not content:
            raise RuntimeError("Euria n'a renvoyé aucun contenu exploitable.")

        usage = data.get("usage") or {}
        if usage:
            logger.info(
                "[EuriaClient] {} prompt_tokens={} completion_tokens={} total_tokens={}",
                operation,
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                usage.get("total_tokens", "?"),
            )
        return content

    def _post_chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            self._url,
            json=payload,
            headers=self._request_headers(),
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        enable_web_search: bool | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messages": messages,
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if enable_web_search is None:
            enable_web_search = False
        if enable_web_search:
            payload["enable_web_search"] = True
        return payload

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._bearer}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _choice_message(data: dict[str, Any]) -> dict[str, Any]:
        return (((data.get("choices") or [{}])[0]).get("message") or {})

    @classmethod
    def _extract_message_content(cls, data: dict[str, Any]) -> str:
        message = cls._choice_message(data)
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                str(part.get("text") or "").strip()
                for part in content
                if isinstance(part, dict) and str(part.get("type") or "") == "text"
            ]
            return "\n".join(part for part in text_parts if part).strip()
        return ""

    @classmethod
    def _should_retry_for_reasoning_only(cls, data: dict[str, Any], max_tokens: int) -> bool:
        if max_tokens >= cls._RETRY_MAX_TOKENS:
            return False
        choice = (data.get("choices") or [{}])[0]
        finish_reason = str(choice.get("finish_reason") or "").strip().lower()
        if finish_reason != "length":
            return False
        if cls._extract_message_content(data):
            return False
        message = cls._choice_message(data)
        return bool(str(message.get("reasoning") or "").strip())

    @classmethod
    def _extract_delta_content(cls, delta: dict[str, Any]) -> str:
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and str(part.get("type") or "") == "text"
            ]
            return "".join(text_parts)
        return ""

    def _stream_payload(
        self,
        payload: dict[str, Any],
        *,
        operation: str,
        max_tokens: int,
    ) -> Iterator[str]:
        stream_payload = dict(payload)
        stream_payload["stream"] = True
        saw_content = False
        saw_reasoning = False
        finish_reason = ""

        with requests.post(
            self._url,
            json=stream_payload,
            headers=self._request_headers(),
            timeout=120,
            stream=True,
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    continue
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                finish_reason = str(choice.get("finish_reason") or finish_reason)
                if str(delta.get("reasoning") or "").strip():
                    saw_reasoning = True

                content = self._extract_delta_content(delta)
                if content:
                    saw_content = True
                    yield content

        is_web_search = bool(payload.get("enable_web_search"))
        retry_ceil = self._WEB_SEARCH_MAX_TOKENS if is_web_search else self._RETRY_MAX_TOKENS
        if not saw_content and saw_reasoning and finish_reason.strip().lower() == "length" and max_tokens < retry_ceil:
            retry_payload = dict(payload)
            retry_payload["max_tokens"] = min(retry_ceil, max(max_tokens * 4 if is_web_search else max_tokens * 2, 8000 if is_web_search else 2200))
            logger.info(
                "[EuriaClient] {} retrying truncated reasoning-only stream with max_tokens={} (web_search={})",
                operation,
                retry_payload["max_tokens"],
                is_web_search,
            )
            yield from self._stream_payload(retry_payload, operation=operation, max_tokens=retry_payload["max_tokens"])
            return

        if not saw_content:
            raise RuntimeError("Euria n'a renvoyé aucun contenu exploitable.")

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "stream",
        enable_web_search: bool | None = None,
    ) -> Iterator[str]:
        payload = self._build_payload(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_web_search=enable_web_search,
        )
        yield from self._stream_payload(payload, operation=operation, max_tokens=max_tokens)
