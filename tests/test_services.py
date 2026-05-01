from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.services import ServiceManager


class _FakeThread:
    def __init__(self, target=None, daemon=None, name=None):
        self.target = target
        self.daemon = daemon
        self.name = name
        self.started = False

    def start(self):
        self.started = True


@pytest.mark.unit
class TestServiceManager:
    def test_init_data_dirs_creates_expected_directories(self, tmp_settings):
        manager = ServiceManager.__new__(ServiceManager)

        with patch("src.services.settings", tmp_settings):
            ServiceManager._init_data_dirs(manager)

        assert tmp_settings.data_dir.exists()
        assert (tmp_settings.data_dir / "stats").exists()
        assert (tmp_settings.data_dir / "queries").exists()
        assert tmp_settings.graph_dir.exists()
        assert tmp_settings.insights_dir.exists()
        assert tmp_settings.synthesis_dir.exists()

    def test_init_wires_components_with_deferred_llm_loading(self, tmp_settings, mock_chroma, mock_llm):
        rag_instance = MagicMock()
        indexer_instance = MagicMock()
        graph_instance = MagicMock()
        learner_instance = MagicMock()
        watcher_instance = MagicMock()
        steps: list[str] = []

        with (
            patch("src.services.settings", tmp_settings),
            patch("src.services.configure_logging") as configure_logging,
            patch.object(ServiceManager, "_start_background_services") as start_bg,
            patch("src.database.chroma_store.ChromaStore", return_value=mock_chroma),
            patch("src.ai.mlx_client.MlxClient", return_value=mock_llm),
            patch("src.ai.rag.RAGPipeline", return_value=rag_instance),
            patch("src.indexer.pipeline.IndexingPipeline", return_value=indexer_instance),
            patch("src.graph.builder.GraphBuilder", return_value=graph_instance),
            patch("src.learning.autolearn.AutoLearner", return_value=learner_instance),
            patch("src.vault.watcher.VaultWatcher", return_value=watcher_instance),
        ):
            manager = ServiceManager(on_step=steps.append)

        configure_logging.assert_called_once_with(tmp_settings.log_level, tmp_settings.log_dir)
        mock_llm.load.assert_not_called()
        start_bg.assert_called_once()
        assert manager.chroma is mock_chroma
        assert manager.rag is rag_instance
        assert manager.indexer is indexer_instance
        assert manager.graph is graph_instance
        assert manager.learner is learner_instance
        assert manager.watcher is watcher_instance
        assert len(steps) >= 7
        assert steps[-1] == "✅ Tous les services sont opérationnels"

    def test_signal_ui_active_updates_timestamp_without_autoloading(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.llm = MagicMock()
        manager.llm.is_loaded.return_value = False
        manager._last_ui_activity = 0.0

        with patch("src.services.time.monotonic", return_value=123.4):
            ServiceManager.signal_ui_active(manager)

        assert manager._last_ui_activity == 123.4
        manager.llm.load.assert_not_called()

    def test_stream_activity_marks_manager_active(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager._last_ui_activity = 0.0
        manager._active_stream_count = 0
        manager._stream_lock = MagicMock()
        manager._stream_lock.__enter__ = MagicMock(return_value=manager._stream_lock)
        manager._stream_lock.__exit__ = MagicMock(return_value=False)

        with patch("src.services.time.monotonic", side_effect=[123.4, 125.0]):
            ServiceManager.enter_stream(manager)
            assert ServiceManager.is_ui_active(manager) is True
            ServiceManager.exit_stream(manager)

        assert manager._active_stream_count == 0
        assert manager._last_ui_activity == 125.0

    def test_is_ui_active_depends_on_idle_timeout(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager._last_ui_activity = 50.0

        with patch("src.services.time.monotonic", return_value=100.0):
            assert ServiceManager.is_ui_active(manager) is True

        with patch("src.services.time.monotonic", return_value=1000.0):
            assert ServiceManager.is_ui_active(manager) is False

    def test_is_scheduler_active_depends_on_setting_and_processing_status(self, tmp_settings):
        manager = ServiceManager.__new__(ServiceManager)
        manager.learner = SimpleNamespace(processing_status={"active": True})

        with patch("src.services.settings", tmp_settings):
            tmp_settings.autolearn_enabled = True
            assert ServiceManager.is_scheduler_active(manager) is True
            tmp_settings.autolearn_enabled = False
            assert ServiceManager.is_scheduler_active(manager) is False

    def test_start_background_services_starts_watcher_learner_thread_and_watchdog(self, tmp_settings):
        manager = ServiceManager.__new__(ServiceManager)
        manager.watcher = MagicMock()
        manager.learner = MagicMock()
        created_threads: list[_FakeThread] = []

        def _thread_factory(*, target=None, daemon=None, name=None):
            thread = _FakeThread(target=target, daemon=daemon, name=name)
            created_threads.append(thread)
            return thread

        with (
            patch("src.services.settings", tmp_settings),
            patch("src.services.threading.Thread", side_effect=_thread_factory),
            patch.object(ServiceManager, "_start_model_watchdog") as start_watchdog,
        ):
            tmp_settings.autolearn_enabled = True
            tmp_settings.autolearn_allow_background_llm = True
            ServiceManager._start_background_services(manager)

        manager.watcher.start.assert_called_once()
        manager.learner.start.assert_called_once()
        assert created_threads[0].target == manager._initial_index
        assert created_threads[0].started is True
        start_watchdog.assert_called_once()

    def test_start_background_services_skips_learner_when_disabled(self, tmp_settings):
        manager = ServiceManager.__new__(ServiceManager)
        manager.watcher = MagicMock()
        manager.learner = MagicMock()

        with (
            patch("src.services.settings", tmp_settings),
            patch("src.services.threading.Thread", return_value=_FakeThread()),
            patch.object(ServiceManager, "_start_model_watchdog"),
        ):
            tmp_settings.autolearn_enabled = False
            ServiceManager._start_background_services(manager)

        manager.learner.start.assert_not_called()

    def test_start_model_watchdog_spawns_thread(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.llm = MagicMock()
        created_threads: list[_FakeThread] = []

        def _thread_factory(*, target=None, daemon=None, name=None):
            thread = _FakeThread(target=target, daemon=daemon, name=name)
            created_threads.append(thread)
            return thread

        with patch("src.services.threading.Thread", side_effect=_thread_factory):
            ServiceManager._start_model_watchdog(manager)

        assert created_threads[0].name == "model-watchdog"
        assert created_threads[0].started is True

    def test_model_watchdog_unloads_model_when_ui_and_scheduler_are_idle(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.llm = MagicMock()
        manager.llm.is_loaded.return_value = True
        manager.is_ui_active = MagicMock(return_value=False)
        manager.is_scheduler_active = MagicMock(return_value=False)
        created_threads: list[_FakeThread] = []

        def _thread_factory(*, target=None, daemon=None, name=None):
            thread = _FakeThread(target=target, daemon=daemon, name=name)
            created_threads.append(thread)
            return thread

        with patch("src.services.threading.Thread", side_effect=_thread_factory):
            ServiceManager._start_model_watchdog(manager)

        with patch("src.services.time.sleep", side_effect=[None, RuntimeError("stop")]):
            with pytest.raises(RuntimeError):
                created_threads[0].target()

        manager.llm.unload.assert_called_once()

    def test_model_watchdog_logs_warning_when_unload_check_fails(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.llm = MagicMock()
        manager.llm.is_loaded.side_effect = [RuntimeError("boom")]
        manager.is_ui_active = MagicMock(return_value=False)
        manager.is_scheduler_active = MagicMock(return_value=False)
        created_threads: list[_FakeThread] = []

        def _thread_factory(*, target=None, daemon=None, name=None):
            thread = _FakeThread(target=target, daemon=daemon, name=name)
            created_threads.append(thread)
            return thread

        with patch("src.services.threading.Thread", side_effect=_thread_factory):
            ServiceManager._start_model_watchdog(manager)

        with (
            patch("src.services.time.sleep", side_effect=[None, RuntimeError("stop")]),
            patch("src.services.logger.warning") as warning,
        ):
            with pytest.raises(RuntimeError):
                created_threads[0].target()

        warning.assert_called_once()

    def test_initial_index_updates_status_and_resets_running_flag(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.indexing_status = {"running": False, "processed": 0, "total": 0, "current": ""}
        manager.indexer = MagicMock()

        def _index_vault(on_progress):
            on_progress("note.md", 1, 3)
            return {"added": 1, "updated": 0, "deleted": 0, "skipped": 2}

        manager.indexer.index_vault.side_effect = _index_vault

        ServiceManager._initial_index(manager)

        assert manager.indexing_status["running"] is False
        assert manager.indexing_status["processed"] == 1
        assert manager.indexing_status["total"] == 3
        assert manager.indexing_status["current"] == "Indexation terminee"

    def test_initial_index_resets_running_flag_on_error(self):
        manager = ServiceManager.__new__(ServiceManager)
        manager.indexing_status = {"running": False, "processed": 0, "total": 0, "current": ""}
        manager.indexer = MagicMock()
        manager.indexer.index_vault.side_effect = RuntimeError("boom")

        ServiceManager._initial_index(manager)

        assert manager.indexing_status["running"] is False
        assert manager.indexing_status["current"] == "Indexation terminee"
