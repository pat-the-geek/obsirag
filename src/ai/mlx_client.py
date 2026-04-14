"""
Client MLX-LM — génération locale sans serveur via Apple MLX (Apple Silicon).
Interface commune du runtime LLM : chat(), stream(), is_available()

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
        # Verrou global d'inférence : MLX/Metal ne supporte pas les appels GPU concurrents
        self._infer_lock = threading.Lock()
        # PERF-12 : cache KV du préfixe système (pré-chauffe différée)
        self._prefix_cache: list | None = None
        self._prefix_text: str | None = None
        self._prefix_warm_offset: int = 0
        self._pending_prefix_messages: list[dict] | None = None
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
            self._prefix_cache = None
            self._prefix_text = None
            self._prefix_warm_offset = 0
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
        """Charge le modèle s'il ne l'est pas déjà, puis pré-chauffe le cache préfixe si configuré."""
        if self._model is None:
            logger.info("Modèle MLX non chargé — chargement automatique en cours…")
            self.load()
        if self._prefix_cache is None and self._pending_prefix_messages is not None:
            self._do_warm_prefix_cache()

    # ---- API publique ----

    # ---- PERF-12 : cache KV préfixe système ----

    def configure_prefix_cache(self, prefix_messages: list[dict]) -> None:
        """Définit le préfixe à mettre en cache KV (ex. prompt système).

        Idempotent.  Si le modèle est déjà chargé, le pré-chauffe immédiatement ;
        sinon, le fera automatiquement au premier appel d'inférence.
        """
        self._pending_prefix_messages = prefix_messages
        if self._model is not None and self._prefix_cache is None:
            self._do_warm_prefix_cache()

    def _do_warm_prefix_cache(self) -> None:
        """Pré-remplit le cache KV pour le préfixe configuré (exécuté une seule fois par session)."""
        if self._pending_prefix_messages is None or self._model is None:
            return
        try:
            import mlx.core as mx
            from mlx_lm.generate import generate_step
            from mlx_lm.models.cache import make_prompt_cache
            from mlx_lm.sample_utils import make_sampler

            prefix_text: str = self._tokenizer.apply_chat_template(
                self._pending_prefix_messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            # Encode le texte sans ajouter un BOS supplémentaire (déjà dans le template)
            prefix_tokens: list[int] = self._tokenizer.encode(
                prefix_text, add_special_tokens=False
            )
            cache = make_prompt_cache(self._model)
            sampler = make_sampler(temp=0.0)
            logger.info(
                f"Pré-chauffe cache KV préfixe système ({len(prefix_tokens)} tokens)…"
            )
            # Un seul pas pour déclencher le prefill et remplir le cache
            for _tok, _lp in generate_step(
                mx.array(prefix_tokens),
                self._model,
                prompt_cache=cache,
                max_tokens=1,
                sampler=sampler,
            ):
                pass
            # Supprime le token généré — on ne veut que les états du préfixe
            for c in cache:
                c.trim(1)
            mx.eval([c.state for c in cache if getattr(c, "keys", None) is not None])
            self._prefix_cache = cache
            self._prefix_text = prefix_text
            self._prefix_warm_offset = cache[0].offset
            logger.info(
                f"Cache KV préfixe prêt — {self._prefix_warm_offset} tokens système mis en cache."
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(f"Échec pré-chauffe cache KV préfixe (fallback sans cache) : {exc}")
            self._prefix_cache = None

    def _reset_prefix_cache(self) -> None:
        """Soft-rewind : repositionne les pointeurs du cache sur la fin du préfixe.

        Supprime les entrées de la requête précédente sans copier ni réallouer les tenseurs.
        """
        if self._prefix_cache is None:
            return
        for c in self._prefix_cache:
            excess = c.offset - self._prefix_warm_offset
            if excess > 0:
                c.trim(excess)

    def _build_suffix_tokens(self, messages: list[dict[str, str]]) -> list[int] | None:
        """Retourne les tokens correspondant au prompt complet MOINS le préfixe mis en cache.

        Retourne None si le prompt ne commence pas par le préfixe attendu (→ fallback).
        """
        if self._prefix_text is None:
            return None
        full_text = self._build_prompt(messages)
        if not full_text.startswith(self._prefix_text):
            return None
        suffix_text = full_text[len(self._prefix_text):]
        return self._tokenizer.encode(suffix_text, add_special_tokens=False)

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

        sampler = make_sampler(temp=temperature)
        parts: list[str] = []
        last: Any = None

        # PERF-12 : chemin cache préfixe système
        if self._prefix_cache is not None:
            suffix_tokens = self._build_suffix_tokens(messages)
            if suffix_tokens is not None:
                import mlx.core as mx
                with self._infer_lock:
                    self._reset_prefix_cache()
                    for chunk in stream_generate(
                        self._model, self._tokenizer,
                        prompt=mx.array(suffix_tokens),
                        max_tokens=max_tokens, sampler=sampler,
                        prompt_cache=self._prefix_cache,
                    ):
                        if chunk.text:
                            parts.append(chunk.text)
                        last = chunk
                answer = "".join(parts)
                if last:
                    self._track_tokens(last, operation)
                return answer

        # PERF-11 fallback : kv_bits=8 sans cache préfixe
        prompt = self._build_prompt(messages)
        with self._infer_lock:
            for chunk in stream_generate(
                self._model, self._tokenizer,
                prompt=prompt, max_tokens=max_tokens, sampler=sampler,
                kv_bits=8,
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

        sampler = make_sampler(temp=temperature)
        last: Any = None

        # PERF-12 : chemin cache préfixe système
        if self._prefix_cache is not None:
            suffix_tokens = self._build_suffix_tokens(messages)
            if suffix_tokens is not None:
                import mlx.core as mx
                with self._infer_lock:
                    self._reset_prefix_cache()
                    for chunk in stream_generate(
                        self._model, self._tokenizer,
                        prompt=mx.array(suffix_tokens),
                        max_tokens=max_tokens, sampler=sampler,
                        prompt_cache=self._prefix_cache,
                    ):
                        if chunk.text:
                            yield chunk.text
                        last = chunk
                if last:
                    self._track_tokens(last, operation)
                return

        # PERF-11 fallback : kv_bits=8 sans cache préfixe
        prompt = self._build_prompt(messages)
        with self._infer_lock:
            for chunk in stream_generate(
                self._model, self._tokenizer,
                prompt=prompt, max_tokens=max_tokens, sampler=sampler,
                kv_bits=8,
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
