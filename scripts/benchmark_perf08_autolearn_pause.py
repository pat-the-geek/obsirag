#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path

from src.config import settings


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "mean": None, "min": None, "max": None}
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 3)

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": round(statistics.mean(s), 3),
        "min": round(min(s), 3),
        "max": round(max(s), 3),
    }


def _adaptive_pause(base_pause: float, processing_secs: float) -> float:
    return max(0.0, base_pause - min(processing_secs, base_pause))


def main() -> int:
    base_pause = 30.0
    processing_file = settings.processing_times_file

    durations: list[float] = []
    if processing_file.exists():
        data = json.loads(processing_file.read_text(encoding="utf-8"))
        durations = [float(v) for v in data if isinstance(v, (int, float)) and v > 0]

    if not durations:
        print("Aucune donnée de processing_times disponible.")
        return 1

    fixed_pauses = [base_pause for _ in durations]
    adaptive_pauses = [_adaptive_pause(base_pause, d) for d in durations]

    fixed_total_per_note = [d + base_pause for d in durations]
    adaptive_total_per_note = [d + p for d, p in zip(durations, adaptive_pauses)]

    fixed_mean_cycle = statistics.mean(fixed_total_per_note)
    adaptive_mean_cycle = statistics.mean(adaptive_total_per_note)

    fixed_throughput_h = 3600.0 / fixed_mean_cycle if fixed_mean_cycle else 0.0
    adaptive_throughput_h = 3600.0 / adaptive_mean_cycle if adaptive_mean_cycle else 0.0

    throughput_gain_pct = (
        ((adaptive_throughput_h - fixed_throughput_h) / fixed_throughput_h) * 100.0 if fixed_throughput_h else 0.0
    )
    pause_reduction_pct = (
        ((statistics.mean(fixed_pauses) - statistics.mean(adaptive_pauses)) / statistics.mean(fixed_pauses)) * 100.0
        if fixed_pauses
        else 0.0
    )

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": "perf08_autolearn_pause",
        "sample_size": len(durations),
        "base_pause_seconds": base_pause,
        "processing_seconds": _percentiles(durations),
        "fixed_pause_seconds": _percentiles(fixed_pauses),
        "adaptive_pause_seconds": _percentiles(adaptive_pauses),
        "fixed_cycle_seconds": _percentiles(fixed_total_per_note),
        "adaptive_cycle_seconds": _percentiles(adaptive_total_per_note),
        "fixed_estimated_throughput_notes_per_hour": round(fixed_throughput_h, 2),
        "adaptive_estimated_throughput_notes_per_hour": round(adaptive_throughput_h, 2),
        "throughput_gain_pct": round(throughput_gain_pct, 2),
        "pause_reduction_pct": round(pause_reduction_pct, 2),
    }

    out_dir = Path("logs/validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"perf08_autolearn_pause_{stamp}.json"
    latest = out_dir / "perf08_autolearn_pause_latest.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResult file: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
