from __future__ import annotations

import os
from pathlib import Path
import time

import pytest

from src.ui.telemetry_store import (
    apply_report_retention,
    append_fallback_snapshot,
    compute_chroma_trend_alerts,
    compute_fallback_alert_window,
    load_runtime_metrics_last_update,
    load_runtime_metrics_payload,
    load_token_usage_payload,
)


@pytest.mark.unit
class TestTelemetryStore:
    def test_load_token_usage_payload_returns_dict_or_empty(self, tmp_path: Path):
        path = tmp_path / "tokens.json"
        path.write_text('{"cumulative": {"calls": 2}}', encoding="utf-8")

        assert load_token_usage_payload(path) == {"cumulative": {"calls": 2}}
        assert load_token_usage_payload(tmp_path / "missing.json") == {}

    def test_load_runtime_metrics_payload_normalizes_counters_and_summaries(self, tmp_path: Path):
        path = tmp_path / "metrics.json"
        path.write_text('{"counters": {"a": 1}, "summaries": {"b": {"count": 2}}}', encoding="utf-8")

        payload = load_runtime_metrics_payload(path)

        assert payload == {"counters": {"a": 1}, "summaries": {"b": {"count": 2}}}

    def test_load_runtime_metrics_payload_handles_invalid_shape(self, tmp_path: Path):
        path = tmp_path / "metrics_bad.json"
        path.write_text('{"counters": [], "summaries": "x"}', encoding="utf-8")

        payload = load_runtime_metrics_payload(path)

        assert payload == {"counters": {}, "summaries": {}}

    def test_load_runtime_metrics_last_update_returns_formatted_date(self, tmp_path: Path):
        path = tmp_path / "metrics.json"
        path.write_text('{"counters": {}}', encoding="utf-8")

        result = load_runtime_metrics_last_update(path)

        assert result is not None
        # Doit être au format "YYYY-MM-DD HH:MM"
        assert len(result) == 16
        assert result[4] == "-" and result[7] == "-" and result[10] == " " and result[13] == ":"

    def test_load_runtime_metrics_last_update_returns_none_for_missing_file(self, tmp_path: Path):
        result = load_runtime_metrics_last_update(tmp_path / "absent.json")

        assert result is None

    def test_fallback_snapshot_and_sliding_window_alert(self, tmp_path: Path):
        path = tmp_path / "fallback.jsonl"

        append_fallback_snapshot(
            path,
            {
                "autolearn_fs_fallback_insight_glob_total": 1,
                "autolearn_fs_fallback_insight_rglob_total": 0,
                "autolearn_fs_fallback_rename_rglob_total": 0,
            },
            now_ts=100.0,
        )
        append_fallback_snapshot(
            path,
            {
                "autolearn_fs_fallback_insight_glob_total": 2,
                "autolearn_fs_fallback_insight_rglob_total": 2,
                "autolearn_fs_fallback_rename_rglob_total": 1,
            },
            now_ts=160.0,
        )

        alert = compute_fallback_alert_window(
            path,
            window_minutes=2,
            threshold=2,
            now_ts=160.0,
        )

        assert alert.rglob_events_in_window == 3
        assert alert.should_warn is True

    def test_fallback_alert_window_returns_no_warning_when_no_snapshot(self, tmp_path: Path):
        alert = compute_fallback_alert_window(
            tmp_path / "missing.jsonl",
            window_minutes=15,
            threshold=3,
            now_ts=200.0,
        )

        assert alert.rglob_events_in_window == 0
        assert alert.should_warn is False

    def test_append_fallback_snapshot_respects_budget_mb(self, tmp_path: Path):
        path = tmp_path / "fallback.jsonl"

        for index in range(20):
            append_fallback_snapshot(
                path,
                {
                    "autolearn_fs_fallback_insight_glob_total": index,
                    "autolearn_fs_fallback_insight_rglob_total": index,
                    "autolearn_fs_fallback_rename_rglob_total": index,
                },
                now_ts=1000.0 + index,
                max_lines=10_000,
                max_age_days=365,
                max_total_mb=0.0002,
            )

        assert path.exists()
        assert path.stat().st_size <= int(0.0002 * 1024 * 1024) + 256

    def test_compute_chroma_trend_alerts_detects_degradation_over_threshold(self):
        latest = {
            "checks": {
                "build_note_views_ms": {"value": 12.0},
                "cache_hit_us": {"value": 6.0},
                "nine_helpers_ms": {"value": 1.5},
            }
        }
        baseline = {
            "checks": {
                "build_note_views_ms": {"value": 10.0},
                "cache_hit_us": {"value": 5.0},
                "nine_helpers_ms": {"value": 1.0},
            }
        }

        alerts = compute_chroma_trend_alerts(latest, baseline, warn_pct=20.0)

        assert [a.metric for a in alerts] == ["build_note_views_ms", "cache_hit_us", "nine_helpers_ms"]

    def test_apply_report_retention_prunes_by_age_and_count(self, tmp_path: Path):
        report_dir = tmp_path / "reports"
        report_dir.mkdir(parents=True)

        old_json = report_dir / "chroma_perf_local_20200101_000000.json"
        old_md = report_dir / "comparison_local_vs_ci_20200101_000000.md"
        keep_json_1 = report_dir / "chroma_perf_local_20260412_090000.json"
        keep_json_2 = report_dir / "chroma_perf_local_20260412_100000.json"
        keep_json_3 = report_dir / "chroma_perf_local_20260412_110000.json"
        stable = report_dir / "latest_local.json"

        for file_path in (old_json, old_md, keep_json_1, keep_json_2, keep_json_3, stable):
            file_path.write_text("{}", encoding="utf-8")

        very_old = time.time() - (40 * 86400)
        os.utime(old_json, (very_old, very_old))
        os.utime(old_md, (very_old, very_old))

        apply_report_retention(report_dir, max_age_days=30, max_files=2)

        assert not old_json.exists()
        assert not old_md.exists()
        assert stable.exists()
        kept_timestamped = sorted(p.name for p in report_dir.iterdir() if p.name.startswith("chroma_perf_"))
        assert len(kept_timestamped) == 2

    def test_apply_report_retention_prunes_by_budget_mb(self, tmp_path: Path):
        report_dir = tmp_path / "reports"
        report_dir.mkdir(parents=True)

        files = [
            report_dir / "chroma_perf_local_20260412_120000.json",
            report_dir / "chroma_perf_local_20260412_121000.json",
            report_dir / "chroma_perf_local_20260412_122000.json",
        ]
        for index, file_path in enumerate(files):
            file_path.write_text("X" * (1024 + (index * 10)), encoding="utf-8")

        apply_report_retention(
            report_dir,
            max_age_days=365,
            max_files=100,
            max_total_mb=0.0015,
        )

        remaining = [p for p in report_dir.iterdir() if p.name.startswith("chroma_perf_")]
        total_size = sum(path.stat().st_size for path in remaining)
        assert total_size <= int(0.0015 * 1024 * 1024) + 256