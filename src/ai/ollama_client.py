from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import requests
from loguru import logger

from src.config import settings


class OllamaClient:
    """Client OpenAI-compatible pour Ollama (/v1/chat/completions)."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        context_size: int | None = None,
    ) -> None:
        raw_base = (base_url or settings.ollama_base_url or "").strip()
        if not raw_base:
            raw_base = "http://localhost:11434/v1"
        self._base_url = self._normalize_base_url(raw_base)
        self._model = (model or settings.ollama_chat_model or "qwen2.5:7b").strip()
        self._context_size = int(context_size or settings.ollama_context_size or 4096)

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        base = value.rstrip("/")
        return base if base.endswith("/v1") else f"{base}/v1"

    def load(self) -> None:
        return None

    def unload(self) -> None:
        return None

    def is_loaded(self) -> bool:
        return True

    def is_available(self) -> bool:
        return bool(self._base_url and self._model)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "chat",
        enable_web_search: bool | None = None,
    ) -> str:
        del enable_web_search  # non supporté côté Ollama
        payload = self._build_payload(messages, temperature=temperature, max_tokens=max_tokens, stream=False)
        data = self._post_json(payload)
        content = self._extract_message_content(data)
        if not content:
            raise RuntimeError("Ollama n'a renvoyé aucun contenu exploitable.")
        return content

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "stream",
        enable_web_search: bool | None = None,
    ) -> Iterator[str]:
        del enable_web_search  # non supporté côté Ollama
        payload = self._build_payload(messages, temperature=temperature, max_tokens=max_tokens, stream=True)
        yield from self._stream_json_lines(payload, operation=operation)

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            # Ollama accepte options via API OpenAI-compatible.
            "options": {"num_ctx": self._context_size},
        }

    def _request_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def _endpoint(self) -> str:
        return f"{self._base_url}/chat/completions"

    @staticmethod
    def _network_error_message(exc: Exception) -> str:
        msg = str(exc)
        if "Failed to resolve" in msg or "NameResolutionError" in msg or "nodename nor servname" in msg:
            return "Ollama est inaccessible — vérifiez l'adresse réseau configurée."
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            return "Ollama n'a pas répondu dans les délais — service indisponible ou saturé."
        if "Connection refused" in msg or "ConnectionRefusedError" in msg:
            return "Ollama est inaccessible — connexion refusée."
        return "Ollama est temporairement inaccessible."

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                self._endpoint(),
                json=payload,
                headers=self._request_headers(),
                timeout=(10, 180),
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise RuntimeError(self._network_error_message(exc)) from exc

    def _stream_json_lines(self, payload: dict[str, Any], *, operation: str) -> Iterator[str]:
        try:
            resp_ctx = requests.post(
                self._endpoint(),
                json=payload,
                headers=self._request_headers(),
                timeout=(10, 120),
                stream=True,
            )
        except Exception as exc:
            raise RuntimeError(self._network_error_message(exc)) from exc

        with resp_ctx as response:
            try:
                response.raise_for_status()
            except Exception as exc:
                raise RuntimeError(self._network_error_message(exc)) from exc

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break

                try:
                    chunk = json.loads(line)
                except Exception:
                    logger.debug("[OllamaClient] Ligne stream ignorée ({}) : {}", operation, line)
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                text = self._extract_delta_content(delta)
                if text:
                    yield text

    @staticmethod
    def _extract_message_content(data: dict[str, Any]) -> str:
        message = (((data.get("choices") or [{}])[0]).get("message") or {})
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

    @staticmethod
    def _extract_delta_content(delta: dict[str, Any]) -> str:
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