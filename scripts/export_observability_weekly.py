#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.ui.telemetry_store import (
    apply_report_retention,
    compute_chroma_trend_alerts,
    load_fallback_snapshots,
    load_latest_json,
)


def _iso_to_ts(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _compute_weekly_fallback_delta(snapshots: list[dict], now_ts: float) -> dict:
    since = now_ts - (7 * 86400)
    recent = [s for s in snapshots if float(s.get("ts", 0.0)) >= since]
    if not recent:
        return {
            "insight_glob_delta": 0,
            "insight_rglob_delta": 0,
            "rename_rglob_delta": 0,
            "rglob_total_delta": 0,
            "snapshots_in_window": 0,
        }

    first = recent[0].get("counters", {})
    last = recent[-1].get("counters", {})
    insight_glob_delta = max(
        0,
        int(last.get("autolearn_fs_fallback_insight_glob_total", 0))
        - int(first.get("autolearn_fs_fallback_insight_glob_total", 0)),
    )
    insight_rglob_delta = max(
        0,
        int(last.get("autolearn_fs_fallback_insight_rglob_total", 0))
        - int(first.get("autolearn_fs_fallback_insight_rglob_total", 0)),
    )
    rename_rglob_delta = max(
        0,
        int(last.get("autolearn_fs_fallback_rename_rglob_total", 0))
        - int(first.get("autolearn_fs_fallback_rename_rglob_total", 0)),
    )

    return {
        "insight_glob_delta": insight_glob_delta,
        "insight_rglob_delta": insight_rglob_delta,
        "rename_rglob_delta": rename_rglob_delta,
        "rglob_total_delta": insight_rglob_delta + rename_rglob_delta,
        "snapshots_in_window": len(recent),
    }


def _render_weekly_markdown(payload: dict, previous: dict | None) -> str:
    lines = [
        "# Observability Weekly",
        "",
        f"- Week end (UTC): {payload.get('week_end_utc', 'n/a')}",
        f"- Window: {payload.get('window_days', 7)} day(s)",
        "",
        "## Fallback deltas",
        "",
    ]

    fallback = payload.get("fallback", {})
    lines.extend(
        [
            f"- insight_glob_delta: {fallback.get('insight_glob_delta', 0)}",
            f"- insight_rglob_delta: {fallback.get('insight_rglob_delta', 0)}",
            f"- rename_rglob_delta: {fallback.get('rename_rglob_delta', 0)}",
            f"- rglob_total_delta: {fallback.get('rglob_total_delta', 0)}",
            "",
            "## Chroma perf trend",
            "",
        ]
    )

    trend = payload.get("trend", {})
    alerts = trend.get("alerts", [])
    if not alerts:
        lines.append("- No degradation alert vs baseline.")
    else:
        for alert in alerts:
            lines.append(
                "- "
                + f"{alert.get('metric')}: {alert.get('degrade_pct')}% "
                + f"(latest={alert.get('latest_value')}, baseline={alert.get('baseline_value')})"
            )

    if previous:
        prev_fallback = previous.get("fallback", {})
        prev_total = int(prev_fallback.get("rglob_total_delta", 0))
        curr_total = int(fallback.get("rglob_total_delta", 0))
        lines.extend(
            [
                "",
                "## Comparison vs previous weekly export",
                "",
                f"- previous_rglob_total_delta: {prev_total}",
                f"- current_rglob_total_delta: {curr_total}",
                f"- delta: {curr_total - prev_total}",
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    now = datetime.now(UTC)
    now_ts = now.timestamp()

    snapshots = load_fallback_snapshots(settings.fallback_snapshot_file)
    fallback_delta = _compute_weekly_fallback_delta(snapshots, now_ts)

    latest_local = load_latest_json(settings.chroma_perf_reports_dir / "latest_local.json")
    latest_ci = load_latest_json(settings.chroma_perf_reports_dir / "latest_ci.json")
    baseline_local = load_latest_json(settings.chroma_perf_reports_dir / "baseline_local.json")

    trend_alerts = compute_chroma_trend_alerts(
        latest_local,
        baseline_local,
        warn_pct=settings.chroma_perf_trend_warn_pct,
    ) if latest_local and baseline_local else []

    payload = {
        "week_end_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": 7,
        "fallback": fallback_delta,
        "perf": {
            "latest_local_ts": latest_local.get("ts_utc", ""),
            "latest_ci_ts": latest_ci.get("ts_utc", ""),
            "baseline_local_ts": baseline_local.get("ts_utc", ""),
        },
        "trend": {
            "threshold_pct": settings.chroma_perf_trend_warn_pct,
            "alerts": [
                {
                    "metric": alert.metric,
                    "latest_value": alert.latest_value,
                    "baseline_value": alert.baseline_value,
                    "degrade_pct": alert.degrade_pct,
                }
                for alert in trend_alerts
            ],
        },
    }

    report_dir = settings.observability_weekly_reports_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M%S")

    weekly_json = report_dir / f"observability_weekly_{stamp}.json"
    weekly_md = report_dir / f"observability_weekly_{stamp}.md"

    previous = load_latest_json(report_dir / "latest_weekly.json")
    markdown = _render_weekly_markdown(payload, previous)

    weekly_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    weekly_md.write_text(markdown, encoding="utf-8")

    (report_dir / "latest_weekly.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (report_dir / "latest_weekly.md").write_text(markdown, encoding="utf-8")

    apply_report_retention(
        report_dir,
        max_age_days=settings.observability_weekly_retention_days,
        max_files=settings.observability_weekly_max_files,
        max_total_mb=settings.observability_weekly_budget_mb,
        prefixes=("observability_weekly_",),
    )

    print(str(weekly_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
