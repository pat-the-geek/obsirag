#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai.mlx_client import MlxClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.metrics import MetricsRecorder
from scripts.benchmark_baseline import QUERIES_LONG, QUERIES_SHORT

PHASE_KEYS = [
    "resolve_s",
    "retrieval_s",
    "context_build_s",
    "message_build_s",
    "generation_s",
    "postprocess_s",
]

INTERNAL_PHASE_KEYS = [
    "resolve_s",
    "retrieval_s",
    "context_build_s",
    "message_build_s",
    "postprocess_s",
]


@dataclass
class QueryProfile:
    scenario: str
    query: str
    intent: str = "unknown"
    sources: int = 0
    output_chars: int = 0
    total_s: float = 0.0
    phases: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add_phase(self, phase: str, elapsed: float) -> None:
        self.phases[phase] = self.phases.get(phase, 0.0) + elapsed


class PhaseProbe:
    def __init__(self) -> None:
        self.current: QueryProfile | None = None

    def set_current(self, profile: QueryProfile | None) -> None:
        self.current = profile

    def add(self, phase: str, elapsed: float) -> None:
        if self.current is not None:
            self.current.add_phase(phase, elapsed)


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "mean": None, "min": None, "max": None}
    ordered = sorted(values)
    n = len(ordered)

    def pct(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo), 4)

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": round(statistics.mean(ordered), 4),
        "min": round(min(ordered), 4),
        "max": round(max(ordered), 4),
    }


def _round_dict(data: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 4) for key, value in data.items()}


def _wrap_rag_for_profiling(rag: RAGPipeline, probe: PhaseProbe) -> list[tuple[object, str, Any]]:
    originals: list[tuple[object, str, Any]] = []

    def _replace(obj: object, attr: str, new_value: Any) -> None:
        originals.append((obj, attr, getattr(obj, attr)))
        setattr(obj, attr, new_value)

    original_resolve = rag._resolve_query_with_history

    def profiled_resolve(user_query: str, history: list[dict[str, str]]) -> str:
        t0 = time.perf_counter()
        try:
            return original_resolve(user_query, history)
        finally:
            probe.add("resolve_s", time.perf_counter() - t0)

    _replace(rag, "_resolve_query_with_history", profiled_resolve)

    original_retrieve = rag._retrieve

    def profiled_retrieve(query: str, progress_callback=None):
        t0 = time.perf_counter()
        try:
            chunks, intent = original_retrieve(query, progress_callback=progress_callback)
        finally:
            probe.add("retrieval_s", time.perf_counter() - t0)
        if probe.current is not None:
            probe.current.intent = intent
        return chunks, intent

    _replace(rag, "_retrieve", profiled_retrieve)

    original_build_context = rag._build_context

    def profiled_build_context(chunks: list[dict], query: str, intent: str, char_budget: int | None = None) -> str:
        t0 = time.perf_counter()
        try:
            return original_build_context(chunks, query, intent, char_budget=char_budget)
        finally:
            probe.add("context_build_s", time.perf_counter() - t0)

    _replace(rag, "_build_context", profiled_build_context)

    original_build_messages = rag._build_messages

    def profiled_build_messages(
        query: str,
        context: str,
        history: list[dict[str, str]],
        intent: str = "general",
        force_study_answer: bool = False,
        resolved_query: str | None = None,
    ) -> list[dict[str, str]]:
        t0 = time.perf_counter()
        try:
            return original_build_messages(
                query,
                context,
                history,
                intent=intent,
                force_study_answer=force_study_answer,
                resolved_query=resolved_query,
            )
        finally:
            probe.add("message_build_s", time.perf_counter() - t0)

    _replace(rag, "_build_messages", profiled_build_messages)

    original_normalize = rag._normalize_final_answer

    def profiled_normalize(answer: str, query: str, intent: str) -> str:
        t0 = time.perf_counter()
        try:
            return original_normalize(answer, query, intent)
        finally:
            probe.add("postprocess_s", time.perf_counter() - t0)

    _replace(rag, "_normalize_final_answer", profiled_normalize)

    llm = rag._llm
    original_chat = llm.chat

    def profiled_chat(messages: list[dict[str, str]], *args, **kwargs):
        t0 = time.perf_counter()
        try:
            return original_chat(messages, *args, **kwargs)
        finally:
            probe.add("generation_s", time.perf_counter() - t0)

    _replace(llm, "chat", profiled_chat)

    original_stream = llm.stream

    def profiled_stream(messages: list[dict[str, str]], *args, **kwargs):
        raw_stream = original_stream(messages, *args, **kwargs)
        t0 = time.perf_counter()

        def _iter():
            try:
                for token in raw_stream:
                    yield token
            finally:
                probe.add("generation_s", time.perf_counter() - t0)

        return _iter()

    _replace(llm, "stream", profiled_stream)
    return originals


def _restore_wrapped(originals: list[tuple[object, str, Any]]) -> None:
    for obj, attr, original in reversed(originals):
        setattr(obj, attr, original)


def _profile_queries(rag: RAGPipeline, scenario: str, queries: list[str]) -> list[QueryProfile]:
    probe = PhaseProbe()
    originals = _wrap_rag_for_profiling(rag, probe)
    results: list[QueryProfile] = []

    try:
        for query in queries:
            sample = QueryProfile(scenario=scenario, query=query)
            probe.set_current(sample)
            t0 = time.perf_counter()
            stream, sources = rag.query_stream(user_query=query, chat_history=[])
            output_chars = 0
            for token in stream:
                output_chars += len(token)
            sample.total_s = time.perf_counter() - t0
            sample.sources = len(sources)
            sample.output_chars = output_chars
            results.append(sample)
            probe.set_current(None)
    finally:
        probe.set_current(None)
        _restore_wrapped(originals)

    return results


def _summarize_samples(samples: list[QueryProfile]) -> dict[str, Any]:
    totals = [sample.total_s for sample in samples]
    output_chars = [float(sample.output_chars) for sample in samples]
    phase_series: dict[str, list[float]] = {key: [] for key in PHASE_KEYS}
    phase_totals: dict[str, float] = {key: 0.0 for key in PHASE_KEYS}

    for sample in samples:
        for key in PHASE_KEYS:
            value = float(sample.phases.get(key, 0.0))
            phase_series[key].append(value)
            phase_totals[key] += value

    total_phase_time = sum(phase_totals.values())
    phase_shares = {
        key: ((value / total_phase_time) * 100.0 if total_phase_time else 0.0)
        for key, value in phase_totals.items()
    }

    return {
        "samples": len(samples),
        "total_s": _percentiles(totals),
        "output_chars": _percentiles(output_chars),
        "phase_stats_s": {key: _percentiles(values) for key, values in phase_series.items()},
        "phase_totals_s": _round_dict(phase_totals),
        "phase_share_pct": _round_dict(phase_shares),
    }


def _select_hotspot(summary_by_scenario: dict[str, dict[str, Any]]) -> dict[str, Any]:
    aggregate_totals: dict[str, float] = {key: 0.0 for key in PHASE_KEYS}
    for summary in summary_by_scenario.values():
        for key, value in summary["phase_totals_s"].items():
            aggregate_totals[key] += float(value)

    total_measured = sum(aggregate_totals.values())
    aggregate_shares = {
        key: ((value / total_measured) * 100.0 if total_measured else 0.0)
        for key, value in aggregate_totals.items()
    }
    dominant_phase = max(aggregate_totals, key=aggregate_totals.get)
    internal_candidate_phase = max(INTERNAL_PHASE_KEYS, key=aggregate_totals.get)
    internal_candidate_share = aggregate_shares[internal_candidate_phase]

    rust_go = internal_candidate_share >= 20.0
    decision = "GO" if rust_go else "NO-GO"
    rationale = (
        f"Phase dominante globale: {dominant_phase} ({aggregate_shares[dominant_phase]:.2f}% du temps mesure). "
        f"Meilleure phase applicative interne: {internal_candidate_phase} ({internal_candidate_share:.2f}%)."
    )
    if not rust_go:
        rationale += " Aucun hotspot interne n'atteint le seuil de 20% pour justifier un pilote Rust." 

    return {
        "aggregate_phase_totals_s": _round_dict(aggregate_totals),
        "aggregate_phase_share_pct": _round_dict(aggregate_shares),
        "dominant_phase": dominant_phase,
        "internal_candidate_phase": internal_candidate_phase,
        "internal_candidate_share_pct": round(internal_candidate_share, 2),
        "rust_go_no_go": decision,
        "rationale": rationale,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark PERF-09 hotspot profiling")
    parser.add_argument("--short-limit", type=int, default=5, help="Nombre de requêtes du scénario A à profiler")
    parser.add_argument("--long-limit", type=int, default=5, help="Nombre de requêtes du scénario B à profiler")
    args = parser.parse_args()

    short_queries = QUERIES_SHORT[: max(1, args.short_limit)]
    long_queries = QUERIES_LONG[: max(1, args.long_limit)]

    chroma = ChromaStore()
    llm = MlxClient()
    llm.load()
    rag = RAGPipeline(
        chroma,
        llm,
        metrics=MetricsRecorder(lambda: settings.data_dir / "stats" / "perf09_bench_metrics.json"),
    )

    profiled: dict[str, list[QueryProfile]] = {
        "A": _profile_queries(rag, "A", short_queries),
        "B": _profile_queries(rag, "B", long_queries),
    }

    summary_by_scenario = {
        key: _summarize_samples(samples)
        for key, samples in profiled.items()
    }
    hotspot = _select_hotspot(summary_by_scenario)

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark": "perf09_hotspot",
        "scenario_queries": {
            "A": short_queries,
            "B": long_queries,
        },
        "scenarios": summary_by_scenario,
        "hotspot": hotspot,
        "raw": {
            key: [
                {
                    "query": sample.query,
                    "intent": sample.intent,
                    "sources": sample.sources,
                    "output_chars": sample.output_chars,
                    "total_s": round(sample.total_s, 4),
                    "phases": _round_dict({phase: sample.phases.get(phase, 0.0) for phase in PHASE_KEYS}),
                }
                for sample in samples
            ]
            for key, samples in profiled.items()
        },
    }

    out_dir = Path("logs/validation")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"perf09_hotspot_{stamp}.json"
    latest = out_dir / "perf09_hotspot_latest.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nResult file: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
