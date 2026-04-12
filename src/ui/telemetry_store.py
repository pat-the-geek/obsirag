from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.storage.safe_read import read_json_file, read_text_lines


FALLBACK_COUNTER_KEYS: tuple[str, ...] = (
    "autolearn_fs_fallback_insight_glob_total",
    "autolearn_fs_fallback_insight_rglob_total",
    "autolearn_fs_fallback_rename_rglob_total",
)


@dataclass(frozen=True)
class FallbackAlertWindow:
    window_minutes: int
    rglob_events_in_window: int
    threshold: int
    should_warn: bool
    since_ts: float
    current_ts: float

    @property
    def summary(self) -> str:
        return (
            f"{self.rglob_events_in_window} fallback(s) rglob sur {self.window_minutes} min "
            f"(seuil {self.threshold})"
        )


@dataclass(frozen=True)
class ChromaTrendAlert:
    metric: str
    latest_value: float
    baseline_value: float
    degrade_pct: float
    threshold_pct: float


def compute_chroma_trend_alerts(
    latest_local: dict,
    baseline_local: dict,
    *,
    warn_pct: float,
) -> list[ChromaTrendAlert]:
    """Return alerts when latest local microbench values degrade beyond threshold vs baseline."""
    threshold = max(0.0, float(warn_pct))
    latest_checks = latest_local.get("checks", {}) if isinstance(latest_local, dict) else {}
    baseline_checks = baseline_local.get("checks", {}) if isinstance(baseline_local, dict) else {}
    if not isinstance(latest_checks, dict) or not isinstance(baseline_checks, dict):
        return []

    alerts: list[ChromaTrendAlert] = []
    for metric in ("build_note_views_ms", "cache_hit_us", "nine_helpers_ms"):
        latest_metric = latest_checks.get(metric, {})
        baseline_metric = baseline_checks.get(metric, {})
        if not isinstance(latest_metric, dict) or not isinstance(baseline_metric, dict):
            continue
        try:
            latest_value = float(latest_metric.get("value", 0.0))
            baseline_value = float(baseline_metric.get("value", 0.0))
        except Exception:
            continue
        if baseline_value <= 0:
            continue
        degrade_pct = ((latest_value - baseline_value) / baseline_value) * 100.0
        if degrade_pct >= threshold:
            alerts.append(
                ChromaTrendAlert(
                    metric=metric,
                    latest_value=latest_value,
                    baseline_value=baseline_value,
                    degrade_pct=round(degrade_pct, 2),
                    threshold_pct=threshold,
                )
            )
    return alerts


def load_token_usage_payload(path: Path) -> dict:
    payload = _load_json_payload(path)
    return payload if isinstance(payload, dict) else {}


def load_runtime_metrics_payload(path: Path) -> dict:
    payload = _load_json_payload(path)
    if not isinstance(payload, dict):
        return {}
    counters = payload.get("counters", {})
    summaries = payload.get("summaries", {})
    return {
        "counters": counters if isinstance(counters, dict) else {},
        "summaries": summaries if isinstance(summaries, dict) else {},
    }


def load_runtime_metrics_last_update(path: Path) -> str | None:
    """Retourne la date de dernière modification du fichier métriques ("YYYY-MM-DD HH:MM"), ou None."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def append_fallback_snapshot(
    path: Path,
    counters: dict,
    *,
    now_ts: float | None = None,
    max_lines: int = 2000,
    max_age_days: int = 14,
    max_total_mb: float = 0.0,
) -> None:
    """Persist a compact fallback counter snapshot (JSONL) for sliding-window alerting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = float(now_ts if now_ts is not None else datetime.now().timestamp())
    payload = {
        "ts": timestamp,
        "counters": {
            key: int(counters.get(key, 0))
            for key in FALLBACK_COUNTER_KEYS
        },
    }

    snapshots = _load_fallback_snapshots(path)
    snapshots.append(payload)

    if max_age_days > 0:
        cutoff = timestamp - (max_age_days * 86400)
        snapshots = [item for item in snapshots if float(item.get("ts", 0.0)) >= cutoff]

    if max_lines > 0 and len(snapshots) > max_lines:
        snapshots = snapshots[-max_lines:]

    if max_total_mb > 0:
        max_bytes = int(float(max_total_mb) * 1024 * 1024)
        snapshots = _trim_snapshots_to_budget(snapshots, max_bytes=max_bytes)

    lines = [json.dumps(item, ensure_ascii=False) for item in snapshots]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compute_fallback_alert_window(
    path: Path,
    *,
    window_minutes: int,
    threshold: int,
    now_ts: float | None = None,
) -> FallbackAlertWindow:
    """Compute a soft warning signal from cumulative fallback counters over a sliding window."""
    window_minutes = max(1, int(window_minutes))
    threshold = max(1, int(threshold))
    current_ts = float(now_ts if now_ts is not None else datetime.now().timestamp())
    since_ts = current_ts - (window_minutes * 60)

    snapshots = _load_fallback_snapshots(path)
    if not snapshots:
        return FallbackAlertWindow(window_minutes, 0, threshold, False, since_ts, current_ts)

    latest = snapshots[-1]
    base = latest
    for item in snapshots:
        if item["ts"] >= since_ts:
            base = item
            break

    current_rglob = int(latest["counters"].get("autolearn_fs_fallback_insight_rglob_total", 0)) + int(
        latest["counters"].get("autolearn_fs_fallback_rename_rglob_total", 0)
    )
    base_rglob = int(base["counters"].get("autolearn_fs_fallback_insight_rglob_total", 0)) + int(
        base["counters"].get("autolearn_fs_fallback_rename_rglob_total", 0)
    )

    delta = max(0, current_rglob - base_rglob)
    return FallbackAlertWindow(
        window_minutes=window_minutes,
        rglob_events_in_window=delta,
        threshold=threshold,
        should_warn=delta >= threshold,
        since_ts=since_ts,
        current_ts=current_ts,
    )


def load_latest_json(path: Path) -> dict:
    payload = _load_json_payload(path)
    return payload if isinstance(payload, dict) else {}


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_report_retention(
    report_dir: Path,
    *,
    max_age_days: int,
    max_files: int,
    max_total_mb: float = 0.0,
    prefixes: tuple[str, ...] = ("chroma_perf_", "comparison_"),
) -> None:
    """Prune timestamped Chroma report artifacts by age then by count."""
    if not report_dir.exists():
        return

    timestamped_files = [
        path
        for path in report_dir.iterdir()
        if path.is_file() and (
            any(path.name.startswith(prefix) for prefix in prefixes)
        )
    ]

    if max_age_days > 0:
        cutoff = datetime.now(UTC).timestamp() - (max_age_days * 86400)
        for path in list(timestamped_files):
            if path.stat().st_mtime < cutoff:
                try:
                    path.unlink()
                except Exception:
                    pass

    timestamped_files = [
        path
        for path in report_dir.iterdir()
        if path.is_file() and (
            any(path.name.startswith(prefix) for prefix in prefixes)
        )
    ]
    timestamped_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if max_files > 0 and len(timestamped_files) > max_files:
        for path in timestamped_files[max_files:]:
            try:
                path.unlink()
            except Exception:
                pass

    if max_total_mb > 0:
        max_bytes = int(float(max_total_mb) * 1024 * 1024)
        timestamped_files = [
            path
            for path in report_dir.iterdir()
            if path.is_file() and any(path.name.startswith(prefix) for prefix in prefixes)
        ]
        timestamped_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        total_bytes = sum(path.stat().st_size for path in timestamped_files)
        for path in reversed(timestamped_files):
            if total_bytes <= max_bytes:
                break
            try:
                file_size = path.stat().st_size
                path.unlink()
                total_bytes -= file_size
            except Exception:
                pass


def load_fallback_snapshots(path: Path) -> list[dict]:
    return _load_fallback_snapshots(path)


def _load_json_payload(path: Path):
    if not path.exists():
        return {}
    return read_json_file(path, default={})


def _load_fallback_snapshots(path: Path) -> list[dict]:
    snapshots: list[dict] = []
    for line in read_text_lines(path, default=[], errors="replace"):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        ts = item.get("ts")
        counters = item.get("counters")
        if not isinstance(ts, (int, float)) or not isinstance(counters, dict):
            continue
        snapshots.append(
            {
                "ts": float(ts),
                "counters": {
                    key: int(counters.get(key, 0))
                    for key in FALLBACK_COUNTER_KEYS
                },
            }
        )
    snapshots.sort(key=lambda entry: entry["ts"])
    return snapshots


def _trim_snapshots_to_budget(snapshots: list[dict], *, max_bytes: int) -> list[dict]:
    if max_bytes <= 0:
        return snapshots
    encoded = [json.dumps(item, ensure_ascii=False) for item in snapshots]
    total = sum(len(line.encode("utf-8")) + 1 for line in encoded)
    start = 0
    while total > max_bytes and start < len(encoded):
        total -= len(encoded[start].encode("utf-8")) + 1
        start += 1
    return snapshots[start:]