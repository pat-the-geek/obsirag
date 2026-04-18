from __future__ import annotations

import io
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


def _fake_prefix_cache(offsets: list[int]):
    cache = []
    for offset in offsets:
        item = MagicMock()
        item.offset = offset
        item.state = f"state-{offset}"
        item.keys = True
        cache.append(item)
    return cache


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

    def test_configure_prefix_cache_warms_immediately_when_model_loaded(self):
        client = MlxClient()
        client._model = "model"

        with patch.object(client, "_do_warm_prefix_cache") as warm:
            client.configure_prefix_cache([{"role": "system", "content": "Tu es utile."}])

        assert client._pending_prefix_messages == [{"role": "system", "content": "Tu es utile."}]
        warm.assert_called_once_with()

    def test_ensure_loaded_triggers_load_and_warm_prefix_cache(self):
        client = MlxClient()
        client._pending_prefix_messages = [{"role": "system", "content": "x"}]

        def _load_side_effect():
            client._model = "loaded-model"

        with (
            patch.object(client, "load", side_effect=_load_side_effect) as load,
            patch.object(client, "_do_warm_prefix_cache") as warm,
        ):
            client._ensure_loaded()

        load.assert_called_once_with()
        warm.assert_called_once_with()

    def test_reset_prefix_cache_trims_only_excess_tokens(self):
        cache_a = MagicMock(offset=7)
        cache_b = MagicMock(offset=4)
        client = MlxClient()
        client._prefix_cache = [cache_a, cache_b]
        client._prefix_warm_offset = 4

        client._reset_prefix_cache()

        cache_a.trim.assert_called_once_with(3)
        cache_b.trim.assert_not_called()

    def test_build_suffix_tokens_returns_none_without_matching_prefix(self):
        client = MlxClient()
        client._tokenizer = MagicMock()

        assert client._build_suffix_tokens([{"role": "user", "content": "bonjour"}]) is None

        client._prefix_text = "SYSTEM"
        with patch.object(client, "_build_prompt", return_value="OTHER prompt"):
            assert client._build_suffix_tokens([{"role": "user", "content": "bonjour"}]) is None

    def test_build_suffix_tokens_encodes_only_suffix_when_prefix_matches(self):
        client = MlxClient()
        client._prefix_text = "SYSTEM"
        client._tokenizer = MagicMock()
        client._tokenizer.encode.return_value = [4, 5]

        with patch.object(client, "_build_prompt", return_value="SYSTEM user prompt"):
            suffix = client._build_suffix_tokens([{"role": "user", "content": "bonjour"}])

        assert suffix == [4, 5]
        client._tokenizer.encode.assert_called_once_with(" user prompt", add_special_tokens=False)

    def test_chat_uses_prefix_cache_path_when_suffix_tokens_exist(self):
        tokenizer = MagicMock()
        chunks = [
            SimpleNamespace(text="Salut ", prompt_tokens=6, generation_tokens=1),
            SimpleNamespace(text="cache", prompt_tokens=6, generation_tokens=2),
        ]
        fake_mlx_lm, fake_sample_utils = _fake_mlx_modules(model="model", tokenizer=tokenizer, chunks=chunks)
        fake_core = types.ModuleType("mlx.core")
        fake_core.array = MagicMock(side_effect=lambda value: ("mx-array", value))
        fake_core.eval = MagicMock()
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
        ):
            client = MlxClient()
            client._model = "model"
            client._tokenizer = tokenizer
            client._prefix_cache = [MagicMock(offset=3)]
            client._build_suffix_tokens = MagicMock(return_value=[11, 12])
            client._reset_prefix_cache = MagicMock()

            answer = client.chat([{"role": "user", "content": "bonjour"}], operation="cached_chat")

        assert answer == "Salut cache"
        client._reset_prefix_cache.assert_called_once_with()
        fake_core.array.assert_called_once_with([11, 12])
        assert fake_mlx_lm.stream_generate.call_args.kwargs["prompt_cache"] == client._prefix_cache
        log_usage.assert_called_once()

    def test_stream_uses_prefix_cache_path_when_suffix_tokens_exist(self):
        tokenizer = MagicMock()
        chunks = [
            SimpleNamespace(text="A", prompt_tokens=4, generation_tokens=1),
            SimpleNamespace(text="B", prompt_tokens=4, generation_tokens=2),
        ]
        fake_mlx_lm, fake_sample_utils = _fake_mlx_modules(model="model", tokenizer=tokenizer, chunks=chunks)
        fake_core = types.ModuleType("mlx.core")
        fake_core.array = MagicMock(side_effect=lambda value: ("mx-array", value))
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
        ):
            client = MlxClient()
            client._model = "model"
            client._tokenizer = tokenizer
            client._prefix_cache = [MagicMock(offset=3)]
            client._build_suffix_tokens = MagicMock(return_value=[21])
            client._reset_prefix_cache = MagicMock()

            tokens = list(client.stream([{"role": "user", "content": "bonjour"}], operation="cached_stream"))

        assert tokens == ["A", "B"]
        client._reset_prefix_cache.assert_called_once_with()
        fake_core.array.assert_called_once_with([21])
        log_usage.assert_called_once()

    def test_build_prompt_and_is_available_use_expected_defaults(self):
        client = MlxClient()
        client._tokenizer = MagicMock()
        client._tokenizer.apply_chat_template.return_value = "PROMPT"

        prompt = client._build_prompt([{"role": "user", "content": "bonjour"}])

        assert prompt == "PROMPT"
        assert client.is_available() is True
        client._tokenizer.apply_chat_template.assert_called_once_with(
            [{"role": "user", "content": "bonjour"}],
            tokenize=False,
            add_generation_prompt=True,
        )

    def test_unload_is_noop_when_model_not_loaded(self):
        client = MlxClient()

        with patch("src.ai.mlx_client.gc.collect") as gc_collect:
            client.unload()

        gc_collect.assert_not_called()

    def test_do_warm_prefix_cache_prefills_and_stores_cache(self):
        tokenizer = MagicMock()
        tokenizer.apply_chat_template.return_value = "SYSTEM PROMPT"
        tokenizer.encode.return_value = [1, 2, 3]
        fake_core = types.ModuleType("mlx.core")
        fake_core.array = MagicMock(return_value=("mx-array", [1, 2, 3]))
        fake_core.eval = MagicMock()
        fake_mlx = types.ModuleType("mlx")
        fake_mlx.core = fake_core
        fake_generate = types.ModuleType("mlx_lm.generate")
        fake_generate.generate_step = MagicMock(return_value=iter([(None, None)]))
        fake_cache_module = types.ModuleType("mlx_lm.models.cache")
        cache = _fake_prefix_cache([4, 4])
        fake_cache_module.make_prompt_cache = MagicMock(return_value=cache)
        fake_sample_utils = types.ModuleType("mlx_lm.sample_utils")
        fake_sample_utils.make_sampler = MagicMock(return_value="sampler")

        with patch.dict(
            sys.modules,
            {
                "mlx": fake_mlx,
                "mlx.core": fake_core,
                "mlx_lm.generate": fake_generate,
                "mlx_lm.models.cache": fake_cache_module,
                "mlx_lm.sample_utils": fake_sample_utils,
            },
        ):
            client = MlxClient()
            client._model = "model"
            client._tokenizer = tokenizer
            client._pending_prefix_messages = [{"role": "system", "content": "x"}]

            client._do_warm_prefix_cache()

        assert client._prefix_cache == cache
        assert client._prefix_text == "SYSTEM PROMPT"
        assert client._prefix_warm_offset == 4
        for item in cache:
            item.trim.assert_called_once_with(1)
        fake_core.eval.assert_called_once()
