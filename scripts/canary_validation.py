#!/usr/bin/env python3
"""
PERF-16 — Validation canary progressive ObsiRAG.

Lance 3 phases successives de validation sur le pipeline RAG réel :
  Phase 1 — 10 % : smoke test rapide (QUERIES_SHORT[:2])
  Phase 2 — 30 % : validation élargie   (QUERIES_SHORT[:6])
  Phase 3 — 100 % : run complet          (QUERIES_SHORT + QUERIES_LONG)

Chaque phase évalue :
  - taux d'erreur Python (exceptions)
  - taux de réponses sentinel ("pas dans ton coffre")
  - latence P50 / P95 bout-en-bout
  - décision Go / No-Go selon les seuils PERF-02

Sorties :
  - logs/validation/canary_<timestamp>.json   (résultats détaillés)
  - logs/validation/canary_latest.json        (pointeur stable)

Usage :
  source .venv/bin/activate
  python scripts/canary_validation.py [--phase 1|2|3|all]
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
# Seuils PERF-02 (budgets P95 bout-en-bout par phase)
# ---------------------------------------------------------------------------
# Phase 1 : requêtes courtes seulement → budget A (30 s)
# Phase 2 : A + B mixte → budget intermédiaire (45 s)
# Phase 3 : run complet → budget B (60 s)
_PHASE_BUDGETS: dict[int, dict] = {
    1: {"p95_s": 30.0, "max_error_rate": 0.0, "max_sentinel_rate": 0.5},
    2: {"p95_s": 45.0, "max_error_rate": 0.0, "max_sentinel_rate": 0.6},
    3: {"p95_s": 60.0, "max_error_rate": 0.0, "max_sentinel_rate": 0.7},
}

# Queries par phase
_PHASE_QUERIES: dict[int, list[str]] = {
    1: QUERIES_SHORT[:2],
    2: QUERIES_SHORT[:6],
    3: QUERIES_SHORT + QUERIES_LONG,
}


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

@dataclass
class QueryOutcome:
    phase: int
    query: str
    total_s: float = 0.0
    sentinel: bool = False
    error: str | None = None


@dataclass
class PhaseResult:
    phase: int
    n: int = 0
    n_errors: int = 0
    n_sentinels: int = 0
    latencies: list[float] = field(default_factory=list)
    outcomes: list[QueryOutcome] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.n_errors / max(self.n, 1)

    @property
    def sentinel_rate(self) -> float:
        return self.n_sentinels / max(self.n - self.n_errors, 1)

    @property
    def p50_s(self) -> float:
        if not self.latencies:
            return 0.0
        return round(statistics.median(self.latencies), 3)

    @property
    def p95_s(self) -> float:
        if not self.latencies:
            return 0.0
        k = max(1, int(len(self.latencies) * 0.95))
        return round(sorted(self.latencies)[k - 1], 3)

    def go_nogo(self) -> tuple[bool, list[str]]:
        budget = _PHASE_BUDGETS[self.phase]
        reasons: list[str] = []
        if self.error_rate > budget["max_error_rate"]:
            reasons.append(
                f"taux d'erreur {self.error_rate:.0%} > seuil {budget['max_error_rate']:.0%}"
            )
        if self.sentinel_rate > budget["max_sentinel_rate"]:
            reasons.append(
                f"taux sentinel {self.sentinel_rate:.0%} > seuil {budget['max_sentinel_rate']:.0%}"
            )
        if self.p95_s > budget["p95_s"]:
            reasons.append(
                f"P95 {self.p95_s:.1f}s > budget {budget['p95_s']:.1f}s"
            )
        return (len(reasons) == 0), reasons


# ---------------------------------------------------------------------------
# Exécution d'une phase
# ---------------------------------------------------------------------------

_HARD_SENTINEL_PREFIX = "cette information n'est pas dans ton coffre"


def _run_phase(phase: int, rag: RAGPipeline) -> PhaseResult:
    queries = _PHASE_QUERIES[phase]
    result = PhaseResult(phase=phase, n=len(queries))
    print(f"\n{'='*60}")
    print(f"  Phase {phase} — {len(queries)} requête(s)")
    print(f"{'='*60}")

    for i, query in enumerate(queries, 1):
        outcome = QueryOutcome(phase=phase, query=query)
        print(f"  [{i}/{len(queries)}] {query[:70]}…" if len(query) > 70 else f"  [{i}/{len(queries)}] {query}")
        t0 = time.perf_counter()
        try:
            stream, _ = rag.query_stream(query, chat_history=[])
            answer = "".join(stream)
            outcome.total_s = round(time.perf_counter() - t0, 3)
            outcome.sentinel = answer.strip().lower().startswith(_HARD_SENTINEL_PREFIX)
            if outcome.sentinel:
                result.n_sentinels += 1
        except Exception as exc:
            outcome.total_s = round(time.perf_counter() - t0, 3)
            outcome.error = str(exc)
            result.n_errors += 1
            print(f"    ✗ ERREUR : {exc}")

        result.latencies.append(outcome.total_s)
        result.outcomes.append(outcome)

        status = "✗ ERREUR" if outcome.error else ("⚠ sentinel" if outcome.sentinel else "✓")
        print(f"    {status}  {outcome.total_s:.1f}s")

    go, reasons = result.go_nogo()
    verdict = "GO ✓" if go else "NO-GO ✗"
    print(f"\n  Phase {phase} → {verdict}  |  P50={result.p50_s:.1f}s  P95={result.p95_s:.1f}s"
          f"  erreurs={result.n_errors}/{result.n}  sentinels={result.n_sentinels}/{result.n - result.n_errors}")
    if reasons:
        for r in reasons:
            print(f"    ✗ {r}")

    return result


# ---------------------------------------------------------------------------
# Sérialisation + écriture rapport
# ---------------------------------------------------------------------------

def _build_report(results: list[PhaseResult], started_at: str) -> dict:
    phases_out = []
    overall_go = True
    for r in results:
        go, reasons = r.go_nogo()
        if not go:
            overall_go = False
        phases_out.append({
            "phase": r.phase,
            "n_queries": r.n,
            "n_errors": r.n_errors,
            "n_sentinels": r.n_sentinels,
            "error_rate": round(r.error_rate, 4),
            "sentinel_rate": round(r.sentinel_rate, 4),
            "p50_s": r.p50_s,
            "p95_s": r.p95_s,
            "budget_p95_s": _PHASE_BUDGETS[r.phase]["p95_s"],
            "go": go,
            "reasons": reasons,
            "outcomes": [
                {
                    "query": o.query,
                    "total_s": o.total_s,
                    "sentinel": o.sentinel,
                    "error": o.error,
                }
                for o in r.outcomes
            ],
        })
    return {
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "overall_go": overall_go,
        "phases": phases_out,
        "feature_flags": {
            "rag_backpressure_enabled": settings.rag_backpressure_enabled,
            "rag_answer_cache_enabled": settings.rag_answer_cache_enabled,
        },
    }


def _write_report(report: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = report["started_at"].replace(":", "-").replace("+", "").replace(".", "-")[:19]
    dated = out_dir / f"canary_{ts}.json"
    latest = out_dir / "canary_latest.json"
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    dated.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return dated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Canary validation ObsiRAG (PERF-16)")
    parser.add_argument(
        "--phase",
        choices=["1", "2", "3", "all"],
        default="all",
        help="Phase(s) à exécuter (défaut : all = 1→2→3, s'arrête sur NO-GO)",
    )
    args = parser.parse_args()

    started_at = datetime.now(UTC).isoformat()
    print(f"\nObsiRAG Canary Validation — {started_at}")
    print(f"Modèle : {settings.mlx_chat_model}")
    print(f"Flags  : backpressure={settings.rag_backpressure_enabled}"
          f"  answer_cache={settings.rag_answer_cache_enabled}")

    # Initialisation du pipeline
    chroma = ChromaStore()
    llm = MlxClient()
    metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
    rag = RAGPipeline(chroma=chroma, llm=llm, metrics=metrics)

    phases_to_run = [1, 2, 3] if args.phase == "all" else [int(args.phase)]
    results: list[PhaseResult] = []

    for phase in phases_to_run:
        result = _run_phase(phase, rag)
        results.append(result)
        go, _ = result.go_nogo()
        if not go and args.phase == "all":
            print(f"\n⛔  Arrêt canary — Phase {phase} NO-GO. Les phases suivantes ne seront pas exécutées.")
            break

    # Rapport final
    report = _build_report(results, started_at)
    out_dir = Path("logs/validation")
    report_path = _write_report(report, out_dir)

    print(f"\n{'='*60}")
    overall = "✅ GO GLOBAL" if report["overall_go"] else "❌ NO-GO GLOBAL"
    print(f"  {overall}")
    print(f"  Rapport : {report_path}")
    print(f"{'='*60}\n")

    if not report["overall_go"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
