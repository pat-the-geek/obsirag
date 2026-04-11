from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.ai.mlx_client import MlxClient


def _fake_mlx_modules(*, model=None, tokenizer=None, chunks=None):
    fake_mlx_lm = types.ModuleType("mlx_lm")
    fake_mlx_lm.load = MagicMock(return_value=(model, tokenizer))
    fake_mlx_lm.stream_generate = MagicMock(return_value=iter(chunks or []))

    fake_sample_utils = types.ModuleType("mlx_lm.sample_utils")
    fake_sample_utils.make_sampler = MagicMock(return_value="sampler")
    return fake_mlx_lm, fake_sample_utils


@pytest.mark.unit
class TestMlxClient:
    def test_load_is_idempotent(self):
        tokenizer = MagicMock()
        fake_mlx_lm, fake_sample_utils = _fake_mlx_modules(
            model="model",
            tokenizer=tokenizer,
        )

        with patch.dict(
            sys.modules,
            {"mlx_lm": fake_mlx_lm, "mlx_lm.sample_utils": fake_sample_utils},
        ):
            client = MlxClient()
            client.load()
            client.load()

        assert client.is_loaded() is True
        assert fake_mlx_lm.load.call_count == 1

    def test_chat_autoloads_builds_prompt_and_tracks_tokens(self):
        tokenizer = MagicMock()
        tokenizer.apply_chat_template.return_value = "PROMPT"
        chunks = [
            SimpleNamespace(text="Bonjour ", prompt_tokens=12, generation_tokens=1),
            SimpleNamespace(text="monde", prompt_tokens=12, generation_tokens=2),
        ]
        fake_mlx_lm, fake_sample_utils = _fake_mlx_modules(
            model="model",
            tokenizer=tokenizer,
            chunks=chunks,
        )

        with (
            patch.dict(
                sys.modules,
                {"mlx_lm": fake_mlx_lm, "mlx_lm.sample_utils": fake_sample_utils},
            ),
            patch("src.ai.mlx_client.log_token_usage") as log_usage,
        ):
            client = MlxClient()
            answer = client.chat([
                {"role": "system", "content": "Tu es utile."},
                {"role": "user", "content": "Dis bonjour"},
            ], operation="rag_query")

        assert answer == "Bonjour monde"
        tokenizer.apply_chat_template.assert_called_once()
        fake_sample_utils.make_sampler.assert_called_once_with(temp=0.3)
        fake_mlx_lm.stream_generate.assert_called_once()
        log_usage.assert_called_once()

    def test_stream_yields_tokens_and_unload_clears_model(self):
        tokenizer = MagicMock()
        tokenizer.apply_chat_template.return_value = "PROMPT"
        chunks = [
            SimpleNamespace(text="A", prompt_tokens=5, generation_tokens=1),
            SimpleNamespace(text="B", prompt_tokens=5, generation_tokens=2),
            SimpleNamespace(text="", prompt_tokens=5, generation_tokens=3),
        ]
        fake_mlx_lm, fake_sample_utils = _fake_mlx_modules(
            model="model",
            tokenizer=tokenizer,
            chunks=chunks,
        )
        fake_core = types.ModuleType("mlx.core")
        fake_core.metal = SimpleNamespace(clear_cache=MagicMock())
        fake_mlx = types.ModuleType("mlx")
        fake_mlx.core = fake_core

        with (
            patch.dict(
                sys.modules,
                {
                    "mlx_lm": fake_mlx_lm,
                    "mlx_lm.sample_utils": fake_sample_utils,
                    "mlx": fake_mlx,
                    "mlx.core": fake_core,
                },
            ),
            patch("src.ai.mlx_client.log_token_usage") as log_usage,
            patch("src.ai.mlx_client.gc.collect") as gc_collect,
        ):
            client = MlxClient()
            tokens = list(client.stream([{"role": "user", "content": "x"}], operation="stream"))
            client.unload()

        assert tokens == ["A", "B"]
        assert client.is_loaded() is False
        gc_collect.assert_called_once()
        fake_core.metal.clear_cache.assert_called_once()
        log_usage.assert_called_once()
