from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.ui import services_cache


@pytest.mark.unit
class TestServicesCache:
    def test_is_services_instance_compatible_requires_recent_chroma_helpers(self):
        chroma = SimpleNamespace(
            list_notes_sorted_by_title=lambda: [],
            list_recent_notes=lambda limit=20: [],
            get_backlinks=lambda file_path: [],
        )
        instance = SimpleNamespace(chroma=chroma)

        assert services_cache._is_services_instance_compatible(instance) is True

        incompatible = SimpleNamespace(chroma=SimpleNamespace(list_recent_notes=lambda limit=20: []))
        assert services_cache._is_services_instance_compatible(incompatible) is False

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
        stale = SimpleNamespace(chroma=SimpleNamespace(), signal_ui_active=MagicMock())
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