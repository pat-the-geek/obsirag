#!/usr/bin/env python3
"""Benchmark PERF-07: efficacité de contexte via déduplication des chunks.

Compare deux modes sur les mêmes jeux de chunks:
- no_dedupe: construction du contexte sans la nouvelle déduplication
- dedupe: construction du contexte avec déduplication active

Sortie JSON: logs/validation/perf07_context_dedupe_latest.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import types
from datetime import datetime, UTC
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.metrics import MetricsRecorder


DEFAULT_QUERIES = [
    "Comment relancer l'indexation proprement ?",
    "Quelles sont les optimisations déjà faites côté contexte ?",
    "Comment fonctionne la stratégie de retrieval ?",
    "Comment diagnostiquer un crash lié à Chroma ?",
    "Quels scripts existent pour le benchmark ?",
    "Comment sont regroupés les chunks par note ?",
]


class _DummyLLM:
    def chat(self, *_args, **_kwargs):
        return ""

    def stream(self, *_args, **_kwargs):
        return iter(())


@dataclass
class Sample:
    elapsed_ms: float
    context_chars: int


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def _summarize(samples: list[Sample]) -> dict:
    times = [s.elapsed_ms for s in samples]
    chars = [s.context_chars for s in samples]
    return {
        "samples": len(samples),
        "timings_ms": {
            "mean": statistics.fmean(times) if times else 0.0,
            "p50": _percentile(times, 0.50),
            "p95": _percentile(times, 0.95),
            "p99": _percentile(times, 0.99),
        },
        "context_chars": {
            "mean": statistics.fmean(chars) if chars else 0.0,
            "p50": _percentile(chars, 0.50),
            "p95": _percentile(chars, 0.95),
            "p99": _percentile(chars, 0.99),
        },
    }


def _run_mode(
    *,
    mode: str,
    queries: list[str],
    runs: int,
    build_context: Callable[[list[dict], str, str], str],
    fetch_chunks: Callable[[str], list[dict]],
) -> dict:
    all_samples: list[Sample] = []

    for _ in range(runs):
        for query in queries:
            chunks = fetch_chunks(query)
            t0 = time.perf_counter()
            context = build_context(chunks, query, "rag")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            all_samples.append(Sample(elapsed_ms=elapsed_ms, context_chars=len(context)))

    return {
        "mode": mode,
        **_summarize(all_samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark PERF-07 context dedupe")
    parser.add_argument("--runs", type=int, default=8, help="Nombre de runs par requête")
    parser.add_argument("--out", type=Path, default=Path("logs/validation/perf07_context_dedupe_latest.json"))
    args = parser.parse_args()

    chroma = ChromaStore()
    rag = RAGPipeline(
        chroma,
        _DummyLLM(),
        metrics=MetricsRecorder(lambda: settings.data_dir / "stats" / "perf07_bench_metrics.json"),
    )
    prompting = rag._answer_prompting

    queries = DEFAULT_QUERIES

    def fetch_chunks(query: str) -> list[dict]:
        chunks, _ = rag._retrieve(query)
        return chunks

    original_dedupe = prompting._dedupe_context_chunks
    original_render = prompting.render_context_from_seen_notes

    def no_dedupe(chunks: list[dict]) -> list[dict]:
        return chunks

    def legacy_render_context(self, seen_notes: dict[str, list[dict]], char_budget: int | None) -> str:
        cfg = self._owner._get_settings()
        parts: list[str] = []
        budget = char_budget if char_budget is not None else cfg.max_context_chars

        for file_path, note_chunks in seen_notes.items():
            if budget <= 0:
                break
            title = note_chunks[0]["metadata"].get("note_title", file_path)
            date_mod = note_chunks[0]["metadata"].get("date_modified", "")[:10]
            header = f"### [{title}] ({date_mod})"
            parts.append(header)
            budget -= len(header)

            for chunk in note_chunks:
                if budget <= 0:
                    break
                section = chunk["metadata"].get("section_title", "")
                text = chunk["text"][: cfg.max_chunk_chars]
                if len(chunk["text"]) > cfg.max_chunk_chars:
                    text += "…"
                line = (f"**{section}** — {text}") if section else text
                if len(line) <= budget:
                    parts.append(line)
                    budget -= len(line)
                else:
                    parts.append(line[:budget] + "…")
                    budget = 0
            parts.append("")

        return "\n".join(parts)

    # Baseline: sans déduplication
    prompting._dedupe_context_chunks = no_dedupe
    prompting.render_context_from_seen_notes = types.MethodType(legacy_render_context, prompting)
    no_dedupe_stats = _run_mode(
        mode="no_dedupe",
        queries=queries,
        runs=args.runs,
        build_context=prompting.build_context,
        fetch_chunks=fetch_chunks,
    )

    # Variante: avec déduplication
    prompting._dedupe_context_chunks = original_dedupe
    prompting.render_context_from_seen_notes = original_render
    dedupe_stats = _run_mode(
        mode="dedupe",
        queries=queries,
        runs=args.runs,
        build_context=prompting.build_context,
        fetch_chunks=fetch_chunks,
    )

    # Restaurer l'état original
    prompting._dedupe_context_chunks = original_dedupe
    prompting.render_context_from_seen_notes = original_render

    baseline_p95 = no_dedupe_stats["timings_ms"]["p95"]
    optimized_p95 = dedupe_stats["timings_ms"]["p95"]
    baseline_chars = no_dedupe_stats["context_chars"]["mean"]
    optimized_chars = dedupe_stats["context_chars"]["mean"]

    p95_gain_pct = ((baseline_p95 - optimized_p95) / baseline_p95 * 100.0) if baseline_p95 else 0.0
    chars_reduction_pct = ((baseline_chars - optimized_chars) / baseline_chars * 100.0) if baseline_chars else 0.0

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": "perf07_context_dedupe",
        "runs": args.runs,
        "queries": queries,
        "no_dedupe": no_dedupe_stats,
        "dedupe": dedupe_stats,
        "gain_pct_on_p95": p95_gain_pct,
        "context_chars_reduction_pct_on_mean": chars_reduction_pct,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = args.out.parent / f"perf07_context_dedupe_{stamp}.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResult file: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
