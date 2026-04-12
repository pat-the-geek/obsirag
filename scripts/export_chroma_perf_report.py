#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings
from src.database.chroma_store import ChromaStore
from src.ui.telemetry_store import apply_report_retention


def _is_ci_env() -> bool:
    return os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}


def _perf_threshold(local_value: float, *, ci_factor: float) -> float:
    return local_value * ci_factor if _is_ci_env() else local_value


def _build_store(notes: list[dict]) -> MagicMock:
    store = MagicMock()
    store._note_views_cache = None
    store._note_views_ts = 0.0
    store._list_notes_ts = 0.0
    store._count_ts = 0.0
    store.list_notes = MagicMock(return_value=notes)
    store._build_note_views = lambda *a, s=store, **kw: ChromaStore._build_note_views(s, *a, **kw)
    store._get_note_views = lambda *a, s=store, **kw: ChromaStore._get_note_views(s, *a, **kw)

    for method_name in (
        "count_notes",
        "list_note_folders",
        "list_note_tags",
        "list_notes_sorted_by_title",
        "list_recent_notes",
        "list_notes_by_type",
        "list_user_notes",
        "list_generated_notes",
        "get_backlinks",
    ):
        method = getattr(ChromaStore, method_name)
        setattr(store, method_name, lambda *a, m=method, s=store, **kw: m(s, *a, **kw))
    return store


def _measure_chroma_views() -> dict:
    notes_500 = [
        {
            "file_path": f"notes/n{i}.md",
            "title": f"Note {i}",
            "date_modified": "2026-04-01T10:00:00",
            "tags": [f"tag{i % 8}"],
            "wikilinks": [f"n{(i + 1) % 500}"],
        }
        for i in range(500)
    ]
    store_500 = _build_store(notes_500)

    t0 = time.perf_counter()
    ChromaStore._get_note_views(store_500)
    build_note_views_ms = (time.perf_counter() - t0) * 1000.0

    notes_200 = [
        {
            "file_path": f"n{i}.md",
            "title": f"Note {i}",
            "date_modified": "",
            "tags": [f"t{i % 5}"],
            "wikilinks": [],
        }
        for i in range(200)
    ]
    store_200 = _build_store(notes_200)
    ChromaStore.count_notes(store_200)
    n_calls = 200
    t0 = time.perf_counter()
    for _ in range(n_calls):
        ChromaStore.count_notes(store_200)
    cache_hit_us = ((time.perf_counter() - t0) / n_calls) * 1_000_000.0

    notes_100 = [
        {
            "file_path": f"folder/n{i}.md",
            "title": f"Note {i}",
            "date_modified": "2026-04-01T10:00:00",
            "tags": [f"t{i % 3}"],
            "wikilinks": [f"n{(i + 1) % 100}"],
        }
        for i in range(100)
    ]
    store_100 = _build_store(notes_100)
    ChromaStore.count_notes(store_100)
    t0 = time.perf_counter()
    ChromaStore.count_notes(store_100)
    ChromaStore.list_note_folders(store_100)
    ChromaStore.list_note_tags(store_100)
    ChromaStore.list_notes_sorted_by_title(store_100)
    ChromaStore.list_recent_notes(store_100)
    ChromaStore.list_notes_by_type(store_100, "user")
    ChromaStore.list_user_notes(store_100)
    ChromaStore.list_generated_notes(store_100)
    ChromaStore.get_backlinks(store_100, "folder/n0.md")
    nine_helpers_ms = (time.perf_counter() - t0) * 1000.0

    thresholds = {
        "build_note_views_ms": _perf_threshold(200.0, ci_factor=3.0),
        "cache_hit_us": _perf_threshold(100.0, ci_factor=6.0),
        "nine_helpers_ms": _perf_threshold(0.5, ci_factor=8.0),
    }

    measurements = {
        "build_note_views_ms": build_note_views_ms,
        "cache_hit_us": cache_hit_us,
        "nine_helpers_ms": nine_helpers_ms,
    }

    checks = {
        key: {
            "value": round(value, 4),
            "threshold": round(thresholds[key], 4),
            "ok": bool(value <= thresholds[key]),
        }
        for key, value in measurements.items()
    }

    return {
        "measurements": {k: round(v, 4) for k, v in measurements.items()},
        "thresholds": thresholds,
        "checks": checks,
    }


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_comparison(current: dict, counterpart: dict, *, env: str, other_env: str) -> str:
    curr = current.get("checks", {})
    other = counterpart.get("checks", {})
    lines = [
        f"# Comparatif Chroma perf ({env} vs {other_env})",
        "",
        f"- Horodatage {env}: {current.get('ts_utc', 'inconnu')}",
        f"- Horodatage {other_env}: {counterpart.get('ts_utc', 'inconnu')}",
        "",
        "| Métrique | Valeur " + env + " | Valeur " + other_env + " | Seuil " + env + " | Statut " + env + " |",
        "| --- | ---: | ---: | ---: | --- |",
    ]

    for metric in ("build_note_views_ms", "cache_hit_us", "nine_helpers_ms"):
        c = curr.get(metric, {})
        o = other.get(metric, {})
        lines.append(
            "| "
            + metric
            + " | "
            + str(c.get("value", "-"))
            + " | "
            + str(o.get("value", "-"))
            + " | "
            + str(c.get("threshold", "-"))
            + " | "
            + ("OK" if c.get("ok") else "KO")
            + " |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    env = "ci" if _is_ci_env() else "local"
    other_env = "local" if env == "ci" else "ci"

    report_dir = settings.chroma_perf_reports_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    apply_report_retention(
        report_dir,
        max_age_days=settings.chroma_perf_report_retention_days,
        max_files=settings.chroma_perf_report_max_files,
        max_total_mb=settings.chroma_perf_report_budget_mb,
    )

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    run_payload = {
        "env": env,
        "ts_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stats_source": "synthetic_microbench",
    }
    run_payload.update(_measure_chroma_views())

    report_file = report_dir / f"chroma_perf_{env}_{stamp}.json"
    _write_json(report_file, run_payload)
    _write_json(report_dir / f"latest_{env}.json", run_payload)
    _write_json(report_dir / "latest.json", run_payload)

    counterpart = _load_json(report_dir / f"latest_{other_env}.json")
    if counterpart:
        comparison_md = _render_comparison(run_payload, counterpart, env=env, other_env=other_env)
        comparison_file = report_dir / f"comparison_{env}_vs_{other_env}_{stamp}.md"
        comparison_file.write_text(comparison_md, encoding="utf-8")
        (report_dir / "latest_comparison.md").write_text(comparison_md, encoding="utf-8")

    print(str(report_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
