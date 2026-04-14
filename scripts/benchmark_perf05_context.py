#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.metrics import MetricsRecorder


class _DummyLLM:
    def chat(self, *_args, **_kwargs):
        return ""

    def stream(self, *_args, **_kwargs):
        return iter(())


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "mean": None, "min": None, "max": None}
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 4)

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": round(statistics.mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _run_context_bench(rag: RAGPipeline, *, disable_bulk: bool, loops: int, queries: list[str]) -> dict:
    original_bulk = rag._get_linked_chunks_by_file_paths

    if disable_bulk:
        def _legacy(file_paths: list[str], limit_per_path: int = 2) -> dict[str, list[dict]]:
            return {
                file_path: rag._get_linked_chunks_by_file_path(file_path, limit=limit_per_path)
                for file_path in file_paths
            }

        rag._get_linked_chunks_by_file_paths = _legacy  # type: ignore[method-assign]

    timings_ms: list[float] = []
    context_chars: list[int] = []

    try:
        for _ in range(loops):
            for query in queries:
                chunks, intent = rag._retrieve(query)
                t0 = time.perf_counter()
                context = rag._build_context(chunks, query, intent)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                timings_ms.append(elapsed_ms)
                context_chars.append(len(context))
    finally:
        rag._get_linked_chunks_by_file_paths = original_bulk  # type: ignore[method-assign]

    return {
        "samples": len(timings_ms),
        "timings_ms": _percentiles(timings_ms),
        "context_chars": _percentiles([float(v) for v in context_chars]),
    }


def main() -> int:
    queries = [
        "Quels liens peux-tu faire entre mes différentes notes sur la technique et l'apprentissage ?",
        "Quelles notes mentionnent des objectifs personnels ?",
        "Quels sujets reviennent le plus souvent dans mon coffre ?",
        "Dresse un panorama complet des connaissances contenues dans mon coffre.",
    ]
    loops = 8

    print("[init] Chroma")
    chroma = ChromaStore()
    rag = RAGPipeline(chroma, _DummyLLM(), metrics=MetricsRecorder(lambda: settings.data_dir / "stats" / "perf05_bench_metrics.json"))

    print("[bench] mode legacy (sans bulk)")
    legacy = _run_context_bench(rag, disable_bulk=True, loops=loops, queries=queries)

    print("[bench] mode bulk (PERF-05)")
    bulk = _run_context_bench(rag, disable_bulk=False, loops=loops, queries=queries)

    legacy_p95 = legacy["timings_ms"]["p95"] or 0.0
    bulk_p95 = bulk["timings_ms"]["p95"] or 0.0
    gain_pct = round(((legacy_p95 - bulk_p95) / legacy_p95) * 100.0, 2) if legacy_p95 else 0.0

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "loops": loops,
        "queries": queries,
        "legacy": legacy,
        "bulk": bulk,
        "gain_pct_on_p95": gain_pct,
    }

    out_dir = Path("logs/validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"perf05_context_{stamp}.json"
    latest = out_dir / "perf05_context_latest.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResult file: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
