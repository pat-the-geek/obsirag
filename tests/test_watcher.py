from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.vault.watcher import VaultWatcher, _DebouncedHandler


class _FakeTimer:
    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self.daemon = False
        self.cancelled = False
        self.started = False

    def cancel(self):
        self.cancelled = True

    def start(self):
        self.started = True


@pytest.mark.unit
class TestDebouncedHandler:
    def test_created_modified_deleted_delegate_to_queue(self):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)
        event = SimpleNamespace(src_path="/tmp/note.md")

        with patch.object(handler, "_queue") as queue:
            handler.on_created(event)
            handler.on_modified(event)
            handler.on_deleted(event)

        queue.assert_any_call("/tmp/note.md", "created")
        queue.assert_any_call("/tmp/note.md", "modified")
        queue.assert_any_call("/tmp/note.md", "deleted")

    def test_queue_ignores_non_markdown_files(self):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)

        with patch("src.vault.watcher.threading.Timer") as timer_cls:
            handler._queue("/tmp/image.png", "modified")

        assert handler._pending == {}
        timer_cls.assert_not_called()

    def test_queue_replaces_existing_timer_and_records_latest_event(self):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)
        first_timer = _FakeTimer(0, lambda: None)
        second_timer = _FakeTimer(0, lambda: None)

        with patch(
            "src.vault.watcher.threading.Timer",
            side_effect=[first_timer, second_timer],
        ):
            handler._queue("/tmp/note.md", "created")
            handler._queue("/tmp/note.md", "modified")

        assert first_timer.cancelled is True
        assert second_timer.started is True
        assert handler._pending == {"/tmp/note.md": "modified"}

    def test_flush_routes_events_to_indexer(self):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)
        deleted = "/tmp/deleted.md"
        modified = "/tmp/updated.md"
        handler._pending = {deleted: "deleted", modified: "modified"}

        handler._flush()

        indexer.remove_note.assert_called_once_with(Path(deleted))
        indexer.index_note.assert_called_once_with(Path(modified))
        assert handler._pending == {}

    def test_flush_noop_when_nothing_pending(self):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)

        handler._flush()

        indexer.remove_note.assert_not_called()
        indexer.index_note.assert_not_called()

    def test_flush_logs_error_when_indexing_fails(self):
        indexer = MagicMock()
        indexer.index_note.side_effect = RuntimeError("boom")
        handler = _DebouncedHandler(indexer)
        handler._pending = {"/tmp/updated.md": "modified"}

        with patch("src.vault.watcher.logger.error") as error:
            handler._flush()

        error.assert_called_once()

    def test_on_moved_queues_delete_and_create(self):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)
        event = SimpleNamespace(src_path="/tmp/old.md", dest_path="/tmp/new.md")

        with patch.object(handler, "_queue") as queue:
            handler.on_moved(event)

        assert queue.call_count == 2
        queue.assert_any_call("/tmp/old.md", "deleted")
        queue.assert_any_call("/tmp/new.md", "created")

    def test_flush_skips_reindex_when_content_hash_unchanged(self, tmp_path):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)
        note = tmp_path / "note.md"
        note.write_text("same content", encoding="utf-8")

        handler._pending = {str(note): "modified"}
        handler._flush()

        handler._pending = {str(note): "modified"}
        handler._flush()

        indexer.index_note.assert_called_once_with(note)

    def test_flush_deleted_event_clears_cached_hash(self, tmp_path):
        indexer = MagicMock()
        handler = _DebouncedHandler(indexer)
        note = tmp_path / "note.md"
        note.write_text("content", encoding="utf-8")
        path = str(note)

        handler._pending = {path: "modified"}
        handler._flush()
        assert path in handler._last_indexed_hash

        handler._pending = {path: "deleted"}
        handler._flush()

        assert path not in handler._last_indexed_hash
        indexer.remove_note.assert_called_once_with(note)


@pytest.mark.unit
class TestVaultWatcher:
    def test_start_skips_when_vault_missing(self, tmp_path):
        indexer = MagicMock()
        missing_settings = SimpleNamespace(vault=tmp_path / "absent")

        with (
            patch("src.vault.watcher.settings", missing_settings),
            patch("src.vault.watcher.Observer") as observer_cls,
            patch("src.vault.watcher.logger.warning") as warning,
        ):
            watcher = VaultWatcher(indexer)
            watcher.start()

        observer_cls.assert_not_called()
        warning.assert_called_once()

    def test_start_and_stop_manage_observer_lifecycle(self, tmp_path):
        vault = tmp_path / "vault"
        vault.mkdir()
        observer = MagicMock()
        observer.is_alive.return_value = True
        patched_settings = SimpleNamespace(vault=vault)

        with (
            patch("src.vault.watcher.settings", patched_settings),
            patch("src.vault.watcher.Observer", return_value=observer),
        ):
            watcher = VaultWatcher(MagicMock())
            watcher.start()
            watcher.stop()

        observer.schedule.assert_called_once()
        observer.start.assert_called_once()
        observer.stop.assert_called_once()
        observer.join.assert_called_once_with(timeout=5)

    def test_stop_noop_when_observer_missing_or_not_alive(self):
        watcher = VaultWatcher(MagicMock())
        watcher.stop()

        observer = MagicMock()
        observer.is_alive.return_value = False
        watcher._observer = observer
        watcher.stop()

        observer.stop.assert_not_called()
        observer.join.assert_not_called()
