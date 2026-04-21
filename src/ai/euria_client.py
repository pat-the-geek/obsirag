from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests
from loguru import logger

from src.config import settings


class EuriaClient:
    DEFAULT_MODEL = "qwen3"

    def __init__(self, *, url: str | None = None, bearer: str | None = None, model: str = "qwen3") -> None:
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
        payload: dict[str, Any] = {
            "messages": messages,
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if enable_web_search is None:
            enable_web_search = "/euria/" in self._url
        if enable_web_search:
            payload["enable_web_search"] = True

        response = requests.post(
            self._url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._bearer}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        content = str((((data.get("choices") or [{}])[0]).get("message") or {}).get("content") or "").strip()
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

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "stream",
    ) -> Iterator[str]:
        content = self.chat(messages, temperature=temperature, max_tokens=max_tokens, operation=operation)
        for token in content.split(" "):
            if token:
                yield f"{token} "
