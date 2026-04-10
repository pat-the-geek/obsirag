"""
Client MLX-LM — génération locale sans serveur via Apple MLX (Apple Silicon).
Interface identique à OllamaClient : chat(), stream(), is_available()

Le modèle est chargé à la demande (chargement différé) et peut être déchargé
quand il n'est pas utilisé pour libérer la mémoire GPU/Metal.
"""
from __future__ import annotations

import gc
import threading
from collections.abc import Iterator
from typing import Any

from loguru import logger

from src.config import settings
from src.logger import log_token_usage


class MlxClient:
    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._model_name = settings.mlx_chat_model
        self._load_lock = threading.Lock()
        logger.info(f"MlxClient initialisé (chargement différé) — modèle : {self._model_name}")

    # ---- Gestion du cycle de vie du modèle ----

    def load(self) -> None:
        """Charge le modèle en mémoire GPU/Metal (idempotent, thread-safe)."""
        with self._load_lock:
            if self._model is not None:
                return
            from mlx_lm import load as mlx_load
            logger.info(f"Chargement du modèle MLX : {self._model_name} (peut prendre 30-60 s)…")
            self._model, self._tokenizer = mlx_load(self._model_name)
            logger.info(f"Modèle MLX prêt : {self._model_name}")

    def unload(self) -> None:
        """Libère le modèle de la mémoire GPU/Metal (idempotent, thread-safe)."""
        with self._load_lock:
            if self._model is None:
                return
            self._model = None
            self._tokenizer = None
            try:
                gc.collect()
                import mlx.core as mx
                mx.metal.clear_cache()
            except Exception:
                pass
            logger.info(f"Modèle MLX déchargé : {self._model_name}")

    def is_loaded(self) -> bool:
        """Retourne True si le modèle est actuellement en mémoire."""
        return self._model is not None

    def _ensure_loaded(self) -> None:
        """Charge le modèle s'il ne l'est pas déjà (mécanisme try-load automatique)."""
        if self._model is None:
            logger.info("Modèle MLX non chargé — chargement automatique en cours…")
            self.load()

    # ---- API publique ----

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        operation: str = "chat",
    ) -> str:
        """Appel bloquant — retourne la réponse complète."""
        self._ensure_loaded()
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
        self._ensure_loaded()
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
        """Retourne True — le modèle est toujours disponible via chargement à la demande."""
        return True

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
