#!/usr/bin/env python3
"""
Benchmark PERF-11 / PERF-12 — MLX generation: TPS & TTFT

Mesure deux métriques clés sur des requêtes RAG réelles :
  - TTFT  : Time-To-First-Token  (secondes)
  - TPS   : Tokens Per Second en génération (tokens/s)
  - total : latence bout-en-bout

Scénarios :
  A — chat court  (requêtes QUERIES_SHORT)
  B — chat long   (requêtes QUERIES_LONG)

Résultat écrit dans logs/validation/perf11_mlx_generation_latest.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_baseline import QUERIES_LONG, QUERIES_SHORT
from src.ai.mlx_client import MlxClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.metrics import MetricsRecorder


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    scenario: str
    query: str
    ttft_s: float = 0.0
    tps: float = 0.0
    total_s: float = 0.0
    tokens_generated: int = 0
    output_chars: int = 0
    cache_hit: bool = False  # True si le chemin prompt_cache a été utilisé
    error: str | None = None


# ---------------------------------------------------------------------------
# Instrumentation du client MLX pour capturer TTFT et TPS
# ---------------------------------------------------------------------------

class InstrumentedMlxClient(MlxClient):
    """Sous-classe qui enregistre TTFT et décompte de tokens à chaque inférence."""

    def __init__(self) -> None:
        super().__init__()
        self._last_ttft_s: float = 0.0
        self._last_tps: float = 0.0
        self._last_tokens: int = 0
        self._last_cache_hit: bool = False

    def stream(self, messages, temperature=0.3, max_tokens=2048, operation="stream"):
        """Overrides stream() pour capturer TTFT, TPS et cache_hit."""
        self._ensure_loaded()
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        sampler = make_sampler(temp=temperature)
        last = None

        # Chemin PERF-12 : cache préfixe
        if self._prefix_cache is not None:
            suffix_tokens = self._build_suffix_tokens(messages)
            if suffix_tokens is not None:
                import mlx.core as mx
                t_start = time.perf_counter()
                first_token_time: float | None = None
                token_count = 0
                with self._infer_lock:
                    self._reset_prefix_cache()
                    for chunk in stream_generate(
                        self._model, self._tokenizer,
                        prompt=mx.array(suffix_tokens),
                        max_tokens=max_tokens, sampler=sampler,
                        prompt_cache=self._prefix_cache,
                    ):
                        if chunk.text:
                            if first_token_time is None:
                                first_token_time = time.perf_counter()
                            yield chunk.text
                            token_count += 1
                        last = chunk
                t_end = time.perf_counter()
                self._last_ttft_s = (first_token_time - t_start) if first_token_time else 0.0
                gen_duration = t_end - (first_token_time or t_start)
                self._last_tps = token_count / gen_duration if gen_duration > 0 else 0.0
                self._last_tokens = last.generation_tokens if last else token_count
                self._last_cache_hit = True
                if last:
                    self._track_tokens(last, operation)
                return

        # Chemin PERF-11 : kv_bits=8
        prompt = self._build_prompt(messages)
        t_start = time.perf_counter()
        first_token_time = None
        token_count = 0
        with self._infer_lock:
            for chunk in stream_generate(
                self._model, self._tokenizer,
                prompt=prompt, max_tokens=max_tokens, sampler=sampler,
                kv_bits=8,
            ):
                if chunk.text:
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
                    yield chunk.text
                    token_count += 1
                last = chunk
        t_end = time.perf_counter()
        self._last_ttft_s = (first_token_time - t_start) if first_token_time else 0.0
        gen_duration = t_end - (first_token_time or t_start)
        self._last_tps = token_count / gen_duration if gen_duration > 0 else 0.0
        self._last_tokens = last.generation_tokens if last else token_count
        self._last_cache_hit = False
        if last:
            self._track_tokens(last, operation)


# ---------------------------------------------------------------------------
# Exécution d'un scénario
# ---------------------------------------------------------------------------

def run_scenario(
    rag: RAGPipeline,
    llm: InstrumentedMlxClient,
    queries: list[str],
    scenario_name: str,
    limit: int,
) -> list[QueryResult]:
    results: list[QueryResult] = []
    subset = queries[:limit]
    for i, query in enumerate(subset, 1):
        print(f"  [{scenario_name}] requête {i}/{len(subset)} : {query[:60]}…")
        result = QueryResult(scenario=scenario_name, query=query)
        t0 = time.perf_counter()
        try:
            stream_iter, sources = rag.query_stream(query, chat_history=[])
            output = "".join(stream_iter)
            result.total_s = time.perf_counter() - t0
            result.output_chars = len(output)
            result.ttft_s = llm._last_ttft_s
            result.tps = llm._last_tps
            result.tokens_generated = llm._last_tokens
            result.cache_hit = llm._last_cache_hit
        except Exception as exc:
            result.error = str(exc)
            result.total_s = time.perf_counter() - t0
            print(f"    ERREUR : {exc}")
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Statistiques descriptives
# ---------------------------------------------------------------------------

def _pct(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * p / 100) - 1)
    return sorted_vals[idx]


def aggregate(results: list[QueryResult]) -> dict:
    ok = [r for r in results if r.error is None]
    if not ok:
        return {"n": 0, "errors": len(results)}
    ttfts = [r.ttft_s for r in ok]
    tpss = [r.tps for r in ok if r.tps > 0]
    totals = [r.total_s for r in ok]
    tokens = [r.tokens_generated for r in ok if r.tokens_generated > 0]
    cache_hits = sum(1 for r in ok if r.cache_hit)
    return {
        "n": len(ok),
        "errors": len(results) - len(ok),
        "cache_hits": cache_hits,
        "ttft_mean_s": round(statistics.mean(ttfts), 3) if ttfts else 0,
        "ttft_p50_s": round(_pct(ttfts, 50), 3),
        "ttft_p95_s": round(_pct(ttfts, 95), 3),
        "tps_mean": round(statistics.mean(tpss), 2) if tpss else 0,
        "tps_p50": round(_pct(tpss, 50), 2),
        "tps_p95": round(_pct(tpss, 95), 2),
        "total_mean_s": round(statistics.mean(totals), 3),
        "total_p50_s": round(_pct(totals, 50), 3),
        "total_p95_s": round(_pct(totals, 95), 3),
        "tokens_mean": round(statistics.mean(tokens), 1) if tokens else 0,
    }


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark PERF-11/12 MLX TPS & TTFT")
    parser.add_argument("--scenario", choices=["A", "B", "AB"], default="AB",
                        help="Scénario(s) à exécuter (défaut: AB)")
    parser.add_argument("--limit", type=int, default=5,
                        help="Nombre de requêtes par scénario (défaut: 5)")
    args = parser.parse_args()

    print("=" * 60)
    print("Benchmark PERF-11/12 : TPS & TTFT MLX")
    print("=" * 60)

    llm = InstrumentedMlxClient()
    chroma = ChromaStore()
    metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
    rag = RAGPipeline(chroma, llm, metrics)

    all_results: dict[str, list[QueryResult]] = {}

    if "A" in args.scenario:
        print("\n--- Scénario A (chat court) ---")
        all_results["A"] = run_scenario(rag, llm, QUERIES_SHORT, "A", args.limit)

    if "B" in args.scenario:
        print("\n--- Scénario B (chat long) ---")
        all_results["B"] = run_scenario(rag, llm, QUERIES_LONG, "B", args.limit)

    # Rapport
    report: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "mlx_model": settings.mlx_chat_model,
        "scenarios": {},
        "summary": {},
    }

    print("\n" + "=" * 60)
    print("RÉSULTATS")
    print("=" * 60)
    all_ok: list[QueryResult] = []
    for sc, results in all_results.items():
        stats = aggregate(results)
        all_ok.extend(r for r in results if r.error is None)
        report["scenarios"][sc] = {
            "queries": [
                {
                    "query": r.query[:80],
                    "ttft_s": round(r.ttft_s, 3),
                    "tps": round(r.tps, 2),
                    "tokens": r.tokens_generated,
                    "total_s": round(r.total_s, 3),
                    "cache_hit": r.cache_hit,
                    "error": r.error,
                }
                for r in results
            ],
            "stats": stats,
        }
        print(f"\nScénario {sc} ({stats['n']} requêtes, {stats['cache_hits']} cache hits) :")
        print(f"  TTFT  — mean={stats['ttft_mean_s']}s  P50={stats['ttft_p50_s']}s  P95={stats['ttft_p95_s']}s")
        print(f"  TPS   — mean={stats['tps_mean']} t/s  P50={stats['tps_p50']} t/s  P95={stats['tps_p95']} t/s")
        print(f"  Total — mean={stats['total_mean_s']}s  P50={stats['total_p50_s']}s  P95={stats['total_p95_s']}s")
        print(f"  Tokens générés (moy) : {stats['tokens_mean']}")
        if stats.get("errors"):
            print(f"  ERREURS : {stats['errors']}")

    if all_ok:
        all_ttfts = [r.ttft_s for r in all_ok]
        all_tpss = [r.tps for r in all_ok if r.tps > 0]
        all_totals = [r.total_s for r in all_ok]
        cache_total = sum(1 for r in all_ok if r.cache_hit)
        report["summary"] = {
            "n_total": len(all_ok),
            "cache_hits": cache_total,
            "ttft_mean_s": round(statistics.mean(all_ttfts), 3),
            "ttft_p95_s": round(_pct(all_ttfts, 95), 3),
            "tps_mean": round(statistics.mean(all_tpss), 2) if all_tpss else 0,
            "total_mean_s": round(statistics.mean(all_totals), 3),
            "total_p95_s": round(_pct(all_totals, 95), 3),
        }
        print("\n--- Agrégat global ---")
        s = report["summary"]
        print(f"  TTFT  mean={s['ttft_mean_s']}s  P95={s['ttft_p95_s']}s")
        print(f"  TPS   mean={s['tps_mean']} t/s")
        print(f"  Total mean={s['total_mean_s']}s  P95={s['total_p95_s']}s")
        print(f"  Cache hits : {cache_total}/{len(all_ok)}")

    out_dir = ROOT / "logs" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "perf11_mlx_generation_latest.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapport écrit : {out_file}")


if __name__ == "__main__":
    main()
