"""
Client Ollama (API compatible OpenAI).
- Completion de chat (streaming et non-streaming)
- Suivi automatique de la consommation de tokens à chaque appel
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from loguru import logger
from openai import OpenAI, OpenAIError

from src.config import settings
from src.logger import log_token_usage


class OllamaClient:
    def __init__(self) -> None:
        self._client = OpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",
        )
        self._model = settings.ollama_chat_model
        logger.info(f"OllamaClient → {settings.ollama_base_url} | modèle : {self._model or 'auto'}")

    # ---- API publique ----

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "chat",
    ) -> str:
        """Appel bloquant — retourne la réponse complète."""
        try:
            resp = self._client.chat.completions.create(
                model=self._model or "local-model",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            answer = resp.choices[0].message.content or ""
            self._track_tokens(resp, operation)
            return answer

        except OpenAIError as exc:
            logger.error(f"Ollama chat error : {exc}")
            raise

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "stream",
    ) -> Iterator[str]:
        """Générateur de tokens — pour l'affichage streaming dans l'UI."""
        try:
            stream = self._client.chat.completions.create(
                model=self._model or "local-model",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
            prompt_tokens = 0
            completion_tokens = 0

            for chunk in stream:
                if chunk.usage:
                    prompt_tokens = chunk.usage.prompt_tokens
                    completion_tokens = chunk.usage.completion_tokens
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta

            if prompt_tokens or completion_tokens:
                log_token_usage(
                    operation=operation,
                    model=self._model or "local-model",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    token_stats_file=settings.token_stats_file,
                )

        except OpenAIError as exc:
            logger.error(f"Ollama stream error : {exc}")
            raise

    def is_available(self) -> bool:
        """Vérifie qu'Ollama répond."""
        try:
            self._client.models.list()
            return True
        except Exception:
            return False

    # ---- helpers privés ----

    def _track_tokens(self, resp: Any, operation: str) -> None:
        usage = getattr(resp, "usage", None)
        if usage:
            log_token_usage(
                operation=operation,
                model=self._model or "local-model",
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                token_stats_file=settings.token_stats_file,
            )
