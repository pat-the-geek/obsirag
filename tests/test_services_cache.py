from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import queue

import pytest

from src.ui import services_cache


@pytest.mark.unit
class TestServicesCache:
    @pytest.mark.nrt
    def test_is_services_instance_compatible_requires_recent_chroma_helpers(self):
        def _query_stream(user_query, chat_history=None, progress_callback=None):
            return iter([]), []

        chroma = SimpleNamespace(
            list_notes_sorted_by_title=lambda: [],
            list_note_folders=lambda: [],
            list_note_tags=lambda: [],
            list_notes_by_type=lambda note_type: [],
            list_recent_notes=lambda limit=20: [],
            list_user_notes=lambda: [],
            list_generated_notes=lambda: [],
            count_notes=lambda: 0,
            get_backlinks=lambda file_path: [],
        )
        instance = SimpleNamespace(chroma=chroma, rag=SimpleNamespace(query_stream=_query_stream))

        assert services_cache._is_services_instance_compatible(instance) is True

        incompatible = SimpleNamespace(chroma=SimpleNamespace(list_recent_notes=lambda limit=20: []))
        assert services_cache._is_services_instance_compatible(incompatible) is False

        old_rag_instance = SimpleNamespace(chroma=chroma, rag=SimpleNamespace(query_stream=lambda user_query, chat_history=None: (iter([]), [])))
        assert services_cache._is_services_instance_compatible(old_rag_instance) is False

    @pytest.mark.nrt
    def test_reset_cached_services_clears_singleton_state(self):
        services_cache._services_instance = SimpleNamespace()
        services_cache._init_thread = object()
        services_cache._init_error = RuntimeError("boom")
        services_cache._init_done.set()

        services_cache._reset_cached_services()

        assert services_cache._services_instance is None
        assert services_cache._init_thread is None
        assert services_cache._init_error is None
        assert services_cache._init_done.is_set() is False

    def test_get_services_restarts_init_when_cached_instance_is_incompatible(self):
        stale = SimpleNamespace(chroma=SimpleNamespace(), rag=SimpleNamespace(), signal_ui_active=MagicMock())
        services_cache._services_instance = stale
        services_cache._init_thread = object()
        services_cache._init_error = None
        services_cache._init_done.set()

        fake_st = SimpleNamespace(
            session_state={},
            markdown=MagicMock(),
            columns=MagicMock(return_value=(MagicMock(), MagicMock(), MagicMock())),
            write=MagicMock(),
            error=MagicMock(),
            stop=MagicMock(side_effect=AssertionError("stop should not be called")),
            rerun=MagicMock(side_effect=RuntimeError("rerun")),
        )

        with (
            patch("src.ui.services_cache.st", fake_st),
            patch("src.ui.services_cache._ensure_init_started") as ensure_started,
            patch("src.ui.services_cache.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="rerun"):
                services_cache.get_services()

        ensure_started.assert_called()
        assert services_cache._services_instance is None
        assert fake_st.session_state["_startup_steps"] == [
            "Compatibilite runtime detectee — reconstruction des services…"
        ]

    def test_get_services_renders_last_startup_steps_once_before_returning_ready_instance(self):
        ready = SimpleNamespace(signal_ui_active=MagicMock())
        services_cache._services_instance = ready
        services_cache._init_thread = object()
        services_cache._init_error = None
        services_cache._init_done.clear()
        services_cache._step_queue = queue.Queue()
        services_cache._step_queue.put("🚀 Lancement des services en arrière-plan…")
        services_cache._step_queue.put("✅ Tous les services sont opérationnels")

        fake_col = MagicMock()
        fake_col.__enter__ = MagicMock(return_value=fake_col)
        fake_col.__exit__ = MagicMock(return_value=False)
        fake_st = SimpleNamespace(
            session_state={},
            markdown=MagicMock(),
            columns=MagicMock(return_value=(MagicMock(), fake_col, MagicMock())),
            write=MagicMock(),
            error=MagicMock(),
            stop=MagicMock(side_effect=AssertionError("stop should not be called")),
            rerun=MagicMock(side_effect=RuntimeError("rerun")),
        )

        with (
            patch("src.ui.services_cache.st", fake_st),
            patch("src.ui.services_cache.run_inline_script"),
            patch("src.ui.services_cache._ensure_init_started"),
            patch("src.ui.services_cache._is_services_instance_compatible", return_value=True),
            patch("src.ui.services_cache.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="rerun"):
                services_cache.get_services()

        assert fake_st.session_state["_svc_ready"] is True
        assert fake_st.session_state["_startup_steps"] == [
            "🚀 Lancement des services en arrière-plan…",
            "✅ Tous les services sont opérationnels",
        ]
        fake_st.write.assert_any_call("🚀 Lancement des services en arrière-plan…")
        fake_st.write.assert_any_call("✅ Tous les services sont opérationnels")
        ready.signal_ui_active.assert_not_called()

    def test_get_services_returns_ready_instance_after_final_startup_render(self):
        ready = SimpleNamespace(signal_ui_active=MagicMock())
        services_cache._services_instance = ready
        services_cache._init_thread = object()
        services_cache._init_error = None
        services_cache._init_done.clear()
        services_cache._step_queue = queue.Queue()

        fake_st = SimpleNamespace(
            session_state={"_svc_ready": True, "_startup_steps": ["✅ Tous les services sont opérationnels"]},
            markdown=MagicMock(),
            columns=MagicMock(),
            write=MagicMock(),
            error=MagicMock(),
            stop=MagicMock(side_effect=AssertionError("stop should not be called")),
            rerun=MagicMock(),
        )

        with (
            patch("src.ui.services_cache.st", fake_st),
            patch("src.ui.services_cache.run_inline_script"),
            patch("src.ui.services_cache._ensure_init_started"),
            patch("src.ui.services_cache._is_services_instance_compatible", return_value=True),
        ):
            result = services_cache.get_services()

        assert result is ready
        ready.signal_ui_active.assert_called_once()