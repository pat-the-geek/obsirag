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


def _measure_prepare_context(rag: RAGPipeline, *, force_recompute: bool, loops: int, queries: list[str]) -> dict:
    strategy = rag._retrieval_strategy
    original_hint = strategy._extract_primary_note_hint

    if force_recompute:
        strategy._extract_primary_note_hint = staticmethod(lambda _chunks: None)  # type: ignore[method-assign]

    timings_ms: list[float] = []

    try:
        for _ in range(loops):
            for query in queries:
                chunks, intent = rag._retrieve(query)
                marked = strategy.mark_primary_sources(chunks, query, intent)
                t0 = time.perf_counter()
                _ = strategy.prepare_context_chunks(marked, query, intent)
                timings_ms.append((time.perf_counter() - t0) * 1000.0)
    finally:
        strategy._extract_primary_note_hint = original_hint  # type: ignore[method-assign]

    return {
        "samples": len(timings_ms),
        "timings_ms": _percentiles(timings_ms),
    }


def main() -> int:
    queries = [
        "Quels liens peux-tu faire entre mes différentes notes sur la technique et l'apprentissage ?",
        "Quels sujets reviennent le plus souvent dans mon coffre ?",
        "Dresse un panorama complet des connaissances contenues dans mon coffre.",
    ]
    loops = 12

    print("[init] Chroma")
    chroma = ChromaStore()
    rag = RAGPipeline(chroma, _DummyLLM(), metrics=MetricsRecorder(lambda: settings.data_dir / "stats" / "perf06_bench_metrics.json"))

    print("[bench] mode recompute (sans hint)")
    recompute = _measure_prepare_context(rag, force_recompute=True, loops=loops, queries=queries)

    print("[bench] mode hint (PERF-06)")
    hinted = _measure_prepare_context(rag, force_recompute=False, loops=loops, queries=queries)

    old_p95 = recompute["timings_ms"]["p95"] or 0.0
    new_p95 = hinted["timings_ms"]["p95"] or 0.0
    gain_pct = round(((old_p95 - new_p95) / old_p95) * 100.0, 2) if old_p95 else 0.0

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "loops": loops,
        "queries": queries,
        "recompute": recompute,
        "hint": hinted,
        "gain_pct_on_p95": gain_pct,
    }

    out_dir = Path("logs/validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"perf06_primary_hint_{stamp}.json"
    latest = out_dir / "perf06_primary_hint_latest.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResult file: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
