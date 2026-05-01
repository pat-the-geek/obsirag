from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.logger import configure_logging, log_token_usage


@pytest.mark.unit
class TestLogger:
    def test_configure_logging_adds_console_and_rotating_files(self, tmp_path):
        log_dir = tmp_path / "logs"

        with patch("src.logger.logger") as mock_logger:
            configure_logging("DEBUG", str(log_dir))

        mock_logger.remove.assert_called_once()
        assert mock_logger.add.call_count == 5
        assert log_dir.exists()

    def test_log_token_usage_creates_daily_and_cumulative_stats(self, tmp_path):
        token_stats_file = tmp_path / "stats" / "token_usage.json"
        bound_logger = MagicMock()

        with patch("src.logger.logger.bind", return_value=bound_logger):
            log_token_usage(
                operation="chat",
                model="mlx-test",
                prompt_tokens=12,
                completion_tokens=8,
                token_stats_file=token_stats_file,
            )

        stats = json.loads(token_stats_file.read_text(encoding="utf-8"))
        day_keys = [key for key in stats if key != "cumulative"]

        assert len(day_keys) == 1
        assert stats[day_keys[0]]["chat"] == {"prompt": 12, "completion": 8, "calls": 1}
        assert stats["cumulative"] == {"prompt": 12, "completion": 8, "calls": 1}
        bound_logger.info.assert_called_once()

    def test_log_token_usage_recovers_from_invalid_json_and_overwrites_atomically(self, tmp_path):
        token_stats_file = tmp_path / "stats" / "token_usage.json"
        token_stats_file.parent.mkdir(parents=True, exist_ok=True)
        token_stats_file.write_text("{not-json", encoding="utf-8")

        with patch("src.logger.logger.bind", return_value=MagicMock()):
            log_token_usage(
                operation="search",
                model="mlx-test",
                prompt_tokens=3,
                completion_tokens=2,
                token_stats_file=token_stats_file,
            )

        stats = json.loads(token_stats_file.read_text(encoding="utf-8"))
        day_keys = [key for key in stats if key != "cumulative"]

        assert len(day_keys) == 1
        assert stats[day_keys[0]]["search"] == {"prompt": 3, "completion": 2, "calls": 1}
        assert not token_stats_file.with_suffix(".json.tmp").exists()

    def test_log_token_usage_warns_when_stats_write_fails(self, tmp_path):
        token_stats_file = tmp_path / "stats" / "token_usage.json"

        with (
            patch("src.logger.logger.bind", return_value=MagicMock()),
            patch("pathlib.Path.write_text", side_effect=OSError("disk-full")),
            patch("src.logger.logger.warning") as warning,
        ):
            log_token_usage(
                operation="chat",
                model="mlx-test",
                prompt_tokens=1,
                completion_tokens=1,
                token_stats_file=token_stats_file,
            )

        warning.assert_called_once()