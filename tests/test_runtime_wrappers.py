from __future__ import annotations

import io
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.api import chat_worker, runtime
from src.learning import worker as learning_worker


class _FakeThread:
    def __init__(self, *, target=None, daemon=None, name=None):
        self.target = target
        self.daemon = daemon
        self.name = name
        self.started = False

    def start(self):
        self.started = True


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    runtime._manager = None
    runtime._init_thread = None
    runtime._init_error = None
    runtime._init_done.clear()
    yield
    runtime._manager = None
    runtime._init_thread = None
    runtime._init_error = None
    runtime._init_done.clear()


@pytest.mark.unit
class TestApiRuntime:
    def test_write_startup_snapshot_saves_payload(self):
        store = MagicMock()
        with patch("src.api.runtime._startup_store", return_value=store):
            runtime._write_startup_snapshot(
                ready=False,
                current_step="Initialisation",
                error="boom",
                steps=["a", "b"],
            )

        store.save.assert_called_once_with(
            {
                "ready": False,
                "steps": ["a", "b"],
                "current_step": "Initialisation",
                "error": "boom",
            },
            ensure_ascii=False,
        )

    def test_run_init_stores_manager_on_success(self):
        manager = MagicMock()
        with patch("src.api.runtime.ServiceManager", return_value=manager):
            runtime._run_init()

        assert runtime._manager is manager
        assert runtime._init_error is None
        assert runtime._init_done.is_set() is True

    def test_run_init_persists_error_on_failure(self):
        with (
            patch("src.api.runtime.ServiceManager", side_effect=RuntimeError("startup failed")),
            patch("src.api.runtime._write_startup_snapshot") as snapshot,
        ):
            runtime._run_init()

        assert str(runtime._init_error) == "startup failed"
        snapshot.assert_called_once_with(
            ready=False,
            error="startup failed",
            current_step="Erreur de démarrage",
        )
        assert runtime._init_done.is_set() is True

    def test_ensure_service_manager_started_starts_single_init_thread(self):
        with (
            patch("src.api.runtime._write_startup_snapshot") as snapshot,
            patch("src.api.runtime.Thread", side_effect=lambda **kwargs: _FakeThread(**kwargs)) as thread_cls,
        ):
            runtime.ensure_service_manager_started()
            runtime.ensure_service_manager_started()

        snapshot.assert_called_once_with(ready=False, current_step="Initialisation du runtime ObsiRAG")
        assert thread_cls.call_count == 1
        assert runtime._init_thread is not None
        assert runtime._init_thread.name == "obsirag-api-service-init"
        assert runtime._init_thread.started is True

    def test_get_service_manager_returns_existing_manager_or_raises(self):
        manager = MagicMock()
        runtime._manager = manager
        assert runtime.get_service_manager() is manager

        runtime._manager = None
        runtime._init_error = RuntimeError("unavailable")
        runtime._init_done.set()
        with patch("src.api.runtime.ensure_service_manager_started"):
            with pytest.raises(RuntimeError, match="unavailable"):
                runtime.get_service_manager()


@pytest.mark.unit
class TestChatWorker:
    def test_build_runtime_wires_dependencies(self, tmp_settings):
        metrics = MagicMock()
        chroma = MagicMock()
        llm = MagicMock()
        rag = MagicMock()

        with (
            patch("src.api.chat_worker.settings", tmp_settings),
            patch("src.api.chat_worker.configure_logging") as configure,
            patch("src.api.chat_worker.MetricsRecorder", return_value=metrics) as metrics_cls,
            patch("src.api.chat_worker.ChromaStore", return_value=chroma),
            patch("src.api.chat_worker.MlxClient", return_value=llm),
            patch("src.api.chat_worker.RAGPipeline", return_value=rag) as rag_cls,
        ):
            built_llm, built_rag = chat_worker._build_runtime()

        configure.assert_called_once_with(tmp_settings.log_level, tmp_settings.log_dir)
        metrics_cls.assert_called_once()
        rag_cls.assert_called_once_with(chroma, llm, metrics=metrics)
        assert built_llm is llm
        assert built_rag is rag

    def test_main_requires_prompt(self):
        with patch("src.api.chat_worker.json.load", return_value={"prompt": "   "}):
            with pytest.raises(SystemExit, match="Missing prompt"):
                chat_worker.main()

    def test_main_returns_answer_and_unloads_model(self):
        llm = MagicMock()
        rag = MagicMock()
        rag.query.return_value = ("Bonjour", [{"file": "note.md"}])

        with (
            patch("src.api.chat_worker.json.load", return_value={"prompt": " Salut ", "history": [{"role": "user"}]}),
            patch("src.api.chat_worker._build_runtime", return_value=(llm, rag)),
            patch("src.api.chat_worker.sys.stdout", new=io.StringIO()) as stdout,
        ):
            code = chat_worker.main()

        assert code == 0
        llm.load.assert_called_once_with()
        rag.query.assert_called_once_with("Salut", chat_history=[{"role": "user"}])
        llm.unload.assert_called_once_with()
        assert '"answer": "Bonjour"' in stdout.getvalue()

    def test_main_ignores_unload_failure(self):
        llm = MagicMock()
        llm.unload.side_effect = RuntimeError("gpu busy")
        rag = MagicMock()
        rag.query.return_value = ("Bonjour", [])

        with (
            patch("src.api.chat_worker.json.load", return_value={"prompt": "Salut"}),
            patch("src.api.chat_worker._build_runtime", return_value=(llm, rag)),
            patch("src.api.chat_worker.sys.stdout", new=io.StringIO()),
        ):
            assert chat_worker.main() == 0


@pytest.mark.unit
class TestAutolearnWorker:
    def test_init_builds_runtime_components(self, tmp_settings):
        metrics = MagicMock()
        chroma = MagicMock()
        llm = MagicMock()
        rag = MagicMock()
        indexer = MagicMock()
        learner = MagicMock()

        with (
            patch("src.learning.worker.settings", tmp_settings),
            patch("src.learning.worker.configure_logging") as configure,
            patch("src.learning.worker.MetricsRecorder", return_value=metrics),
            patch("src.learning.worker.ChromaStore", return_value=chroma),
            patch("src.learning.worker.MlxClient", return_value=llm),
            patch("src.learning.worker.RAGPipeline", return_value=rag),
            patch("src.learning.worker.IndexingPipeline", return_value=indexer),
            patch("src.learning.worker.AutoLearner", return_value=learner) as learner_cls,
        ):
            worker = learning_worker.AutolearnWorker()

        configure.assert_called_once_with(tmp_settings.log_level, tmp_settings.log_dir)
        learner_cls.assert_called_once()
        assert learner_cls.call_args.args == (chroma, rag, indexer)
        assert learner_cls.call_args.kwargs["metrics"] is metrics
        assert callable(learner_cls.call_args.kwargs["ui_active_fn"])
        assert learner_cls.call_args.kwargs["ui_active_fn"]() is False
        assert worker._learner is learner

    def test_persist_runtime_writes_next_run_when_job_exists(self):
        worker = learning_worker.AutolearnWorker.__new__(learning_worker.AutolearnWorker)
        worker._stop_event = MagicMock()
        worker._stop_event.is_set.return_value = False
        next_run = datetime(2026, 4, 18, 12, 0, 0)
        worker._learner = MagicMock()
        worker._learner._scheduler.get_job.return_value = SimpleNamespace(next_run_time=next_run)
        worker._started_at = "2026-04-18T11:00:00+00:00"

        with patch("src.learning.worker.save_autolearn_runtime_state") as save_state:
            worker._persist_runtime()

        save_state.assert_called_once()
        payload = save_state.call_args.args[0]
        assert payload["managedBy"] == "worker"
        assert payload["running"] is True
        assert payload["nextRunAt"] == next_run.isoformat()

    def test_persist_runtime_tolerates_scheduler_errors(self):
        worker = learning_worker.AutolearnWorker.__new__(learning_worker.AutolearnWorker)
        worker._stop_event = MagicMock()
        worker._stop_event.is_set.return_value = True
        worker._learner = MagicMock()
        worker._learner._scheduler.get_job.side_effect = RuntimeError("boom")
        worker._started_at = "2026-04-18T11:00:00+00:00"

        with patch("src.learning.worker.save_autolearn_runtime_state") as save_state:
            worker._persist_runtime()

        assert save_state.call_args.args[0]["nextRunAt"] is None
        assert save_state.call_args.args[0]["running"] is False

    def test_handle_signal_sets_stop_event(self):
        worker = learning_worker.AutolearnWorker.__new__(learning_worker.AutolearnWorker)
        worker._stop_event = MagicMock()

        worker._handle_signal(15, None)

        worker._stop_event.set.assert_called_once_with()

    def test_run_starts_stops_and_persists_runtime(self):
        worker = learning_worker.AutolearnWorker.__new__(learning_worker.AutolearnWorker)
        worker._stop_event = MagicMock()
        worker._stop_event.wait.side_effect = [False, True]
        worker._learner = MagicMock()
        worker._llm = MagicMock()
        worker._started_at = "2026-04-18T11:00:00+00:00"

        with (
            patch("src.learning.worker.signal.signal") as signal_fn,
            patch.object(worker, "_persist_runtime") as persist,
            patch("src.learning.worker.save_autolearn_runtime_state") as save_state,
        ):
            worker.run()

        assert signal_fn.call_count == 2
        worker._learner.start.assert_called_once_with()
        worker._learner.stop.assert_called_once_with()
        worker._llm.unload.assert_called_once_with()
        assert persist.call_count == 3
        assert save_state.call_args.args[0]["running"] is False

    def test_run_logs_stop_and_unload_failures(self):
        worker = learning_worker.AutolearnWorker.__new__(learning_worker.AutolearnWorker)
        worker._stop_event = MagicMock()
        worker._stop_event.wait.return_value = True
        worker._learner = MagicMock()
        worker._learner.stop.side_effect = RuntimeError("stop failed")
        worker._llm = MagicMock()
        worker._llm.unload.side_effect = RuntimeError("unload failed")
        worker._started_at = "2026-04-18T11:00:00+00:00"

        with (
            patch("src.learning.worker.signal.signal"),
            patch.object(worker, "_persist_runtime"),
            patch("src.learning.worker.save_autolearn_runtime_state"),
            patch("src.learning.worker.logger.warning") as warning,
        ):
            worker.run()

        assert warning.call_count == 2

    def test_main_builds_worker_and_runs(self):
        instance = MagicMock()
        with patch("src.learning.worker.AutolearnWorker", return_value=instance):
            learning_worker.main()

        instance.run.assert_called_once_with()