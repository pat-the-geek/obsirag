#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_baseline import QUERIES_LONG, QUERIES_SHORT
from src.ai.ollama_client import OllamaClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.metrics import MetricsRecorder


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "mean": None, "min": None, "max": None}

    ordered = sorted(values)
    n = len(ordered)

    def pct(p: float) -> float:
        idx = (p / 100.0) * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo), 3)

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": round(statistics.mean(ordered), 3),
        "min": round(min(ordered), 3),
        "max": round(max(ordered), 3),
    }


class _PhaseTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()
        self.events: list[tuple[str, float]] = []

    def callback(self, payload: dict) -> None:
        phase = str(payload.get("phase") or "?")
        elapsed = time.perf_counter() - self._start
        self.events.append((phase, elapsed))

    def durations(self) -> dict[str, float]:
        by_phase: dict[str, list[float]] = {}
        for phase, ts in self.events:
            by_phase.setdefault(phase, []).append(ts)

        out: dict[str, float] = {}
        for phase, ts_list in by_phase.items():
            out[phase] = round(ts_list[-1] - ts_list[0], 3) if len(ts_list) > 1 else 0.0
        return out


def _run_one(rag: RAGPipeline, query: str, scenario: str) -> dict:
    timer = _PhaseTimer()
    t0 = time.perf_counter()
    try:
        stream, sources = rag.query_stream(
            user_query=query,
            chat_history=[],
            progress_callback=timer.callback,
        )
        answer_parts: list[str] = []
        first_token_at: float | None = None
        for piece in stream:
            if first_token_at is None:
                first_token_at = time.perf_counter()
            answer_parts.append(piece)
        t_end = time.perf_counter()

        answer = "".join(answer_parts)
        total = round(t_end - t0, 3)
        ttft = round((first_token_at - t0), 3) if first_token_at is not None else total
        generation_wall = round((t_end - first_token_at), 3) if first_token_at is not None else 0.0
        chars_per_s = round((len(answer) / generation_wall), 2) if generation_wall > 0 else 0.0
        return {
            "scenario": scenario,
            "query": query,
            "total_s": total,
            "ttft_s": ttft,
            "generation_wall_s": generation_wall,
            "chars_per_s": chars_per_s,
            "sources": len(sources),
            "output_chars": len(answer),
            "phases": timer.durations(),
        }
    except Exception as exc:
        return {
            "scenario": scenario,
            "query": query,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _render_markdown(payload: dict) -> str:
    stats = payload["stats"]
    lines = [
        "# Benchmark Ollama Chat 20",
        "",
        f"Genere le {payload['generated_at']}",
        "",
        f"- Modele chat: {payload['ollama_chat_model']}",
        f"- Embedding: {payload['ollama_embed_model'] or 'fallback CPU'}",
        f"- Base URL: {payload['ollama_base_url']}",
        f"- Runs benchmark: {payload.get('benchmark_runs', 1)}",
        f"- Executions: {payload['ok_count']} ok / {payload['error_count']} erreurs",
        "",
        "## Stats globales",
        "",
        "| Metrique | P50 | P95 | P99 | Min | Max | Moyenne |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for metric in (
        "total_s",
        "ttft_s",
        "generation_wall_s",
        "retrieval_s",
        "sources",
        "output_chars",
        "chars_per_s",
    ):
        m = stats.get(metric) or {}
        if m.get("p50") is None:
            continue
        lines.append(
            f"| {metric} | {m['p50']} | {m['p95']} | {m['p99']} | {m['min']} | {m['max']} | {m['mean']} |"
        )

    lines.extend([
        "",
        "## Stats par scenario",
        "",
        "| Scenario | Count | P50 total | P95 total | P50 TTFT | P50 gen wall | Moyenne total |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])

    for key in ("short", "long"):
        sc = payload["by_scenario"].get(key, {})
        total = (sc.get("stats") or {}).get("total_s") or {}
        ttft = (sc.get("stats") or {}).get("ttft_s") or {}
        gen_wall = (sc.get("stats") or {}).get("generation_wall_s") or {}
        lines.append(
            f"| {key} | {sc.get('count', 0)} | {total.get('p50')} | {total.get('p95')} | {ttft.get('p50')} | {gen_wall.get('p50')} | {total.get('mean')} |"
        )

    if payload["errors"]:
        lines.extend(["", "## Erreurs", ""])
        for item in payload["errors"]:
            lines.append(f"- {item['scenario']}: {item['query']} -> {item['error']}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Ollama Chat 20")
    parser.add_argument("--runs", type=int, default=1, help="Nombre de passes complètes (20 requêtes par run)")
    args = parser.parse_args()
    runs = max(1, args.runs)

    print("=" * 60)
    print("Benchmark Ollama Chat 20")
    print(f"Runs: {runs}")
    print("=" * 60)

    chroma = ChromaStore()
    llm = OllamaClient()
    rag = RAGPipeline(
        chroma,
        llm,
        metrics=MetricsRecorder(lambda: settings.data_dir / "stats" / "benchmark_ollama_chat20_metrics.json"),
    )

    all_runs: list[dict] = []
    for run_idx in range(1, runs + 1):
        print(f"\\n--- Run {run_idx}/{runs} ---")
        for q in QUERIES_SHORT:
            print(f"[short] {q[:70]}...")
            item = _run_one(rag, q, "short")
            item["run"] = run_idx
            all_runs.append(item)
        for q in QUERIES_LONG:
            print(f"[long ] {q[:70]}...")
            item = _run_one(rag, q, "long")
            item["run"] = run_idx
            all_runs.append(item)

    errors = [r for r in all_runs if "error" in r]
    ok = [r for r in all_runs if "error" not in r]

    def _collect(metric: str, *, phase: str | None = None) -> list[float]:
        vals: list[float] = []
        for item in ok:
            if phase is not None:
                vals.append(float((item.get("phases") or {}).get(phase, 0.0)))
            else:
                vals.append(float(item.get(metric, 0.0)))
        return vals

    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "benchmark_runs": runs,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_chat_model": settings.ollama_chat_model,
        "ollama_embed_model": settings.ollama_embed_model,
        "total_runs": len(all_runs),
        "ok_count": len(ok),
        "error_count": len(errors),
        "stats": {
            "total_s": _percentiles(_collect("total_s")),
            "ttft_s": _percentiles(_collect("ttft_s")),
            "generation_wall_s": _percentiles(_collect("generation_wall_s")),
            "retrieval_s": _percentiles(_collect("", phase="retrieval")),
            "sources": _percentiles(_collect("sources")),
            "output_chars": _percentiles(_collect("output_chars")),
            "chars_per_s": _percentiles(_collect("chars_per_s")),
        },
        "by_scenario": {},
        "errors": errors,
        "raw": all_runs,
    }

    for scenario in ("short", "long"):
        subset = [r for r in ok if r.get("scenario") == scenario]
        payload["by_scenario"][scenario] = {
            "count": len(subset),
            "stats": {
                "total_s": _percentiles([float(r.get("total_s", 0.0)) for r in subset]),
                "ttft_s": _percentiles([float(r.get("ttft_s", 0.0)) for r in subset]),
                "generation_wall_s": _percentiles([float(r.get("generation_wall_s", 0.0)) for r in subset]),
            },
        }

    out_dir = ROOT / "logs" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"benchmark_ollama_chat20_{stamp}.json"
    md_path = out_dir / f"benchmark_ollama_chat20_{stamp}.md"
    latest_json = out_dir / "benchmark_ollama_chat20_latest.json"
    latest_md = out_dir / "benchmark_ollama_chat20_latest.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = _render_markdown(payload)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")

    print("\nSorties:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print(f"- errors: {len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
