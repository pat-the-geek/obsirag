from __future__ import annotations

import io
import sys
import runpy
from unittest.mock import MagicMock, patch

import pytest

from src.api import main as api_main
from src.api import runtime as api_runtime
from src.learning import worker as learning_worker


def test_api_main_exports_fastapi_app() -> None:
    assert api_main.app is not None


def test_api_main_run_module_executes_entrypoint_module() -> None:
    existing = sys.modules.pop("src.api.main", None)
    try:
        namespace = runpy.run_module("src.api.main")
    finally:
        if existing is not None:
            sys.modules["src.api.main"] = existing
    assert "app" in namespace


def test_runtime_startup_store_uses_startup_status_file(tmp_settings) -> None:
    with patch("src.api.runtime.settings", tmp_settings):
        store = api_runtime._startup_store()

    assert store._path == tmp_settings.startup_status_file


def test_runtime_ensure_service_manager_started_skips_when_manager_exists() -> None:
    original_manager = api_runtime._manager
    try:
        api_runtime._manager = MagicMock()
        with patch("src.api.runtime.Thread") as thread_cls:
            api_runtime.ensure_service_manager_started()
        thread_cls.assert_not_called()
    finally:
        api_runtime._manager = original_manager


def test_runtime_ensure_service_manager_started_skips_when_thread_exists() -> None:
    original_manager = api_runtime._manager
    original_thread = api_runtime._init_thread
    try:
        api_runtime._manager = None
        api_runtime._init_thread = MagicMock()
        with patch("src.api.runtime.Thread") as thread_cls:
            api_runtime.ensure_service_manager_started()
        thread_cls.assert_not_called()
    finally:
        api_runtime._manager = original_manager
        api_runtime._init_thread = original_thread


def test_runtime_get_service_manager_raises_default_message_when_manager_missing() -> None:
    original_manager = api_runtime._manager
    original_error = api_runtime._init_error
    try:
        api_runtime._manager = None
        api_runtime._init_error = None
        api_runtime._init_done.set()
        with patch("src.api.runtime.ensure_service_manager_started"):
            with pytest.raises(RuntimeError, match="ServiceManager unavailable"):
                api_runtime.get_service_manager()
    finally:
        api_runtime._manager = original_manager
        api_runtime._init_error = original_error
        api_runtime._init_done.clear()


def test_runtime_get_service_manager_returns_manager_after_startup_wait() -> None:
    original_manager = api_runtime._manager
    original_error = api_runtime._init_error
    try:
        expected = MagicMock()
        api_runtime._manager = None
        api_runtime._init_error = None
        api_runtime._init_done.clear()

        def _start():
            api_runtime._manager = expected
            api_runtime._init_done.set()

        with patch("src.api.runtime.ensure_service_manager_started", side_effect=_start):
            assert api_runtime.get_service_manager() is expected
    finally:
        api_runtime._manager = original_manager
        api_runtime._init_error = original_error
        api_runtime._init_done.clear()


def test_learning_worker_module_entrypoint_invokes_main() -> None:
    with patch("src.learning.worker.AutolearnWorker") as worker_cls:
        learning_worker.main()

    worker_cls.return_value.run.assert_called_once_with()


def test_chat_worker_run_module_executes_main_guard() -> None:
    llm = MagicMock()
    rag = MagicMock()
    rag.query.return_value = ("Bonjour", [])

    existing = sys.modules.pop("src.api.chat_worker", None)
    with (
        patch("json.load", return_value={"prompt": "Salut", "history": []}),
        patch("src.logger.configure_logging"),
        patch("src.metrics.MetricsRecorder", return_value=MagicMock()),
        patch("src.database.chroma_store.ChromaStore", return_value=MagicMock()),
        patch("src.ai.mlx_client.MlxClient", return_value=llm),
        patch("src.ai.rag.RAGPipeline", return_value=rag),
        patch("sys.stdout", new=io.StringIO()),
    ):
        try:
            with pytest.raises(SystemExit) as exc:
                runpy.run_module("src.api.chat_worker", run_name="__main__")
        finally:
            if existing is not None:
                sys.modules["src.api.chat_worker"] = existing

    assert exc.value.code == 0


def test_learning_worker_run_module_executes_main_guard() -> None:
    class _ImmediateStopEvent:
        def wait(self, _timeout):
            return True

        def is_set(self):
            return False

        def set(self):
            return None

    existing = sys.modules.pop("src.learning.worker", None)
    with (
        patch("threading.Event", return_value=_ImmediateStopEvent()),
        patch("src.logger.configure_logging"),
        patch("src.metrics.MetricsRecorder", return_value=MagicMock()),
        patch("src.database.chroma_store.ChromaStore", return_value=MagicMock()),
        patch("src.ai.mlx_client.MlxClient", return_value=MagicMock()),
        patch("src.ai.rag.RAGPipeline", return_value=MagicMock()),
        patch("src.indexer.pipeline.IndexingPipeline", return_value=MagicMock()),
        patch("src.learning.autolearn.AutoLearner", return_value=MagicMock()),
        patch("signal.signal"),
        patch("src.learning.runtime_state.save_autolearn_runtime_state"),
    ):
        try:
            runpy.run_module("src.learning.worker", run_name="__main__")
        finally:
            if existing is not None:
                sys.modules["src.learning.worker"] = existing


def test_chat_fallback_worker_run_module_executes_main_guard(tmp_settings) -> None:
    llm = MagicMock()
    rag = MagicMock()
    rag._resolve_query_with_history.return_value = "Ada Lovelace"
    rag._chroma.search.return_value = []

    existing = sys.modules.pop("src.api.chat_fallback_worker", None)
    with (
        patch("json.load", return_value={"prompt": "Salut", "history": []}),
        patch("pathlib.Path.exists", return_value=False),
        patch("src.logger.configure_logging"),
        patch("src.metrics.MetricsRecorder", return_value=MagicMock()),
        patch("src.ai.mlx_client.MlxClient", return_value=llm),
        patch("src.ai.rag.RAGPipeline", return_value=rag),
        patch("sys.stdout", new=io.StringIO()),
    ):
        try:
            with pytest.raises(SystemExit) as exc:
                runpy.run_module("src.api.chat_fallback_worker", run_name="__main__")
        finally:
            if existing is not None:
                sys.modules["src.api.chat_fallback_worker"] = existing

    assert exc.value.code == 0