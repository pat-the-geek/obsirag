"""
Client MLX-LM — génération locale sans serveur via Apple MLX (Apple Silicon).
Interface identique à OllamaClient : chat(), stream(), is_available()

Le modèle est chargé une seule fois dans le constructeur (~30-60 s).
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from loguru import logger

from src.config import settings
from src.logger import log_token_usage


class MlxClient:
    def __init__(self) -> None:
        from mlx_lm import load

        model_name = settings.mlx_chat_model
        logger.info(f"Chargement du modèle MLX : {model_name} (peut prendre 30-60 s)…")
        self._model, self._tokenizer = load(model_name)
        self._model_name = model_name
        logger.info(f"Modèle MLX prêt : {model_name}")

    # ---- API publique ----

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "chat",
    ) -> str:
        """Appel bloquant — retourne la réponse complète."""
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        prompt = self._build_prompt(messages)
        sampler = make_sampler(temp=temperature)
        parts: list[str] = []
        last: Any = None

        for chunk in stream_generate(
            self._model, self._tokenizer,
            prompt=prompt, max_tokens=max_tokens, sampler=sampler,
        ):
            if chunk.text:
                parts.append(chunk.text)
            last = chunk

        answer = "".join(parts)
        if last:
            self._track_tokens(last, operation)
        return answer

    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "stream",
    ) -> Iterator[str]:
        """Générateur de tokens — pour l'affichage streaming dans l'UI."""
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        prompt = self._build_prompt(messages)
        sampler = make_sampler(temp=temperature)
        last: Any = None

        for chunk in stream_generate(
            self._model, self._tokenizer,
            prompt=prompt, max_tokens=max_tokens, sampler=sampler,
        ):
            if chunk.text:
                yield chunk.text
            last = chunk

        if last:
            self._track_tokens(last, operation)

    def is_available(self) -> bool:
        return self._model is not None

    # ---- helpers privés ----

    def _build_prompt(self, messages: list[dict[str, str]]) -> str:
        """Applique le chat template du tokenizer."""
        return self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    def _track_tokens(self, chunk: Any, operation: str) -> None:
        log_token_usage(
            operation=operation,
            model=self._model_name,
            prompt_tokens=chunk.prompt_tokens,
            completion_tokens=chunk.generation_tokens,
            token_stats_file=settings.token_stats_file,
        )
