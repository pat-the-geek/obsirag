#!/usr/bin/env python3
"""
Benchmark baseline ObsiRAG — scenarios de reference Sprint 1.

Lance les 4 scenarios de mesure de performance:
  A — Chat court  : 10 requetes factuelles courtes
  B — Chat long   : 10 requetes de synthese multi-notes
  C — Retrieval   : 10 requetes chronometrees en retrieval pur (sans LLM)
  D — Reindexation: indexation complete a froid

Produit:
  - logs/validation/benchmark_YYYY-MM-DD.json   (donnees brutes)
  - logs/validation/benchmark_YYYY-MM-DD.md     (rapport lisible)
  - logs/validation/benchmark_latest.json       (pointeur stable)
  - logs/validation/benchmark_latest.md         (pointeur stable)

Usage:
  source .venv/bin/activate
  python scripts/benchmark_baseline.py [--scenario A|B|C|D|all] [--runs N]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Ajoute la racine du projet au path ─────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402

# ── Requetes de reference fixees ───────────────────────────────────────────

QUERIES_SHORT = [
    "Quelles notes mentionnent des idées clés dans mon coffre ?",
    "Résume les points clés que j'ai notés sur la productivité.",
    "Quels sont les concepts importants que j'ai retenus sur la productivité ?",
    "Quelles notes mentionnent des objectifs personnels ?",
    "Que sais-tu sur les projets en cours dans mon coffre ?",
    "Quelles notes parlent de projets et d'objectifs ?",
    "Y a-t-il des notes sur l'apprentissage ou la formation ?",
    "Quelles sont les idées principales liées à la technologie ?",
    "Mes notes parlent-elles de lecture ou de livres ?",
    "Quels sujets reviennent le plus souvent dans mon coffre ?",
]

QUERIES_LONG = [
    "Fais une synthèse complète de mes apprentissages majeurs.",
    "Quels sont les apprentissages les plus importants dans toutes mes notes ?",
    "Dresse un bilan des projets et objectifs mentionnés dans mon coffre.",
    "Quels liens peux-tu faire entre mes différentes notes sur la technique et l'apprentissage ?",
    "Synthétise les thèmes récurrents de mon coffre et leur évolution.",
    "Quelles sont les connexions implicites entre mes notes sur la productivité ?",
    "Fais le point sur tout ce que mes notes disent sur la santé et le bien-être.",
    "Résume les idées de mon coffre sur la créativité et l'innovation.",
    "Quels sujets ai-je le plus développés dans mes notes ces derniers mois ?",
    "Dresse un panorama complet des connaissances contenues dans mon coffre.",
]


# ── Timing helpers ─────────────────────────────────────────────────────────

class PhaseTimer:
    """Capture les timestamps de chaque phase via progress_callback."""

    def __init__(self) -> None:
        self.events: list[tuple[str, float]] = []
        self._t_start = time.perf_counter()

    def callback(self, payload: dict) -> None:
        phase = payload.get("phase", "?")
        elapsed = time.perf_counter() - self._t_start
        self.events.append((phase, elapsed))

    def phase_durations(self) -> dict[str, float]:
        """Retourne le temps passe dans chaque phase (premiere apparition -> derniere)."""
        by_phase: dict[str, list[float]] = {}
        for phase, t in self.events:
            by_phase.setdefault(phase, []).append(t)
        result: dict[str, float] = {}
        for phase, times in by_phase.items():
            result[phase] = round(times[-1] - times[0], 3) if len(times) > 1 else 0.0
        return result


def run_query(rag, query: str, history: list | None = None) -> dict:
    """Execute une requete et retourne les timings par phase + total."""
    last_error = None
    for attempt in range(2):
        timer = PhaseTimer()
        t0 = time.perf_counter()
        try:
            stream, sources = rag.query_stream(
                user_query=query,
                chat_history=history or [],
                progress_callback=timer.callback,
            )
            # Consommer le stream pour mesurer le temps de generation complet
            tokens = 0
            for token in stream:
                tokens += len(token)

            total = round(time.perf_counter() - t0, 3)
            durations = timer.phase_durations()

            return {
                "query": query[:60] + "..." if len(query) > 60 else query,
                "total_s": total,
                "phases": durations,
                "sources": len(sources),
                "output_chars": tokens,
                "attempt": attempt + 1,
            }
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                continue

    return {
        "query": query[:60] + "..." if len(query) > 60 else query,
        "error": type(last_error).__name__ if last_error else "UnknownError",
        "error_message": str(last_error) if last_error else "unknown",
    }


def run_retrieval_only(rag, query: str) -> dict:
    """Mesure uniquement le temps de retrieval (sans generation LLM)."""
    t0 = time.perf_counter()
    chunks, intent = rag._retrieve(query)
    elapsed = round(time.perf_counter() - t0, 3)
    return {
        "query": query[:60] + "..." if len(query) > 60 else query,
        "retrieval_s": elapsed,
        "chunks": len(chunks),
        "intent": intent,
    }


# ── Calcul de percentiles ──────────────────────────────────────────────────

def percentiles(values: list[float]) -> dict:
    if not values:
        return {"p50": None, "p95": None, "p99": None, "min": None, "max": None, "mean": None}
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:
        idx = (p / 100) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 3)

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "min": round(min(s), 3),
        "max": round(max(s), 3),
        "mean": round(statistics.mean(s), 3),
    }


# ── Scenarios ──────────────────────────────────────────────────────────────

def scenario_chat(rag, queries: list[str], label: str, runs: int = 1) -> dict:
    """Scenario A ou B: execute les requetes N fois et agregere les stats."""
    print(f"\n▶ Scenario {label} ({len(queries)} requetes x {runs} run(s))")
    all_results: list[dict] = []
    errors: list[dict] = []

    for run in range(runs):
        print(f"  Run {run + 1}/{runs}...")
        for i, q in enumerate(queries):
            print(f"    [{i+1}/{len(queries)}] {q[:50]}...", end=" ", flush=True)
            result = run_query(rag, q)
            if "error" in result:
                print(f"ERREUR {result['error']}")
                errors.append(result)
                continue
            print(f"{result['total_s']}s")
            all_results.append(result)

    totals = [r["total_s"] for r in all_results]
    retrievals = [r["phases"].get("retrieval", 0) for r in all_results]
    generations = [r["phases"].get("generation", 0) for r in all_results]

    return {
        "scenario": label,
        "queries": len(queries),
        "runs": runs,
        "total_executions": len(all_results),
        "errors": len(errors),
        "stats": {
            "total_s": percentiles(totals),
            "retrieval_s": percentiles(retrievals),
            "generation_s": percentiles(generations),
        },
        "raw": all_results,
        "error_details": errors,
    }


def scenario_retrieval_only(rag, queries: list[str], runs: int = 3) -> dict:
    """Scenario C: retrieval pur sans LLM (mesure isolee du hotspot vectoriel)."""
    print(f"\n▶ Scenario C - Retrieval pur ({len(queries)} requetes x {runs} run(s))")
    all_results: list[dict] = []

    for run in range(runs):
        print(f"  Run {run + 1}/{runs}...")
        for i, q in enumerate(queries):
            result = run_retrieval_only(rag, q)
            print(f"    [{i+1}/{len(queries)}] retrieval={result['retrieval_s']}s chunks={result['chunks']} intent={result['intent']}")
            all_results.append(result)

    retrieval_times = [r["retrieval_s"] for r in all_results]
    chunk_counts = [r["chunks"] for r in all_results]

    return {
        "scenario": "C",
        "queries": len(queries),
        "runs": runs,
        "total_executions": len(all_results),
        "stats": {
            "retrieval_s": percentiles(retrieval_times),
            "chunks_returned": percentiles(chunk_counts),
        },
        "raw": all_results,
    }


def scenario_reindexation(indexer) -> dict:
    """Scenario D: reindexation complete a froid (mesure du debit chunking/indexation)."""
    print("\n▶ Scenario D - Reindexation complete")

    progress_log: list[dict] = []

    def on_progress(current_note: str, processed: int, total: int) -> None:
        progress_log.append({"note": current_note, "processed": processed, "total": total})
        if processed % 20 == 0 or processed == total:
            print(f"    {processed}/{total} notes indexees...")

    # Supprimer l'etat pour forcer une reindexation
    state_file = settings.data_dir / "index_state.json"
    state_backup = None
    if state_file.exists():
        state_backup = state_file.read_bytes()
        state_file.unlink()
        indexer._state = {}
        print("  Etat d'index supprime pour forcer le mode premier run.")

    t0 = time.perf_counter()
    stats = indexer.index_vault(on_progress=on_progress)
    total_s = round(time.perf_counter() - t0, 3)

    # Restaurer l'etat
    if state_backup is not None:
        state_file.write_bytes(state_backup)
        indexer._state = indexer._load_state()
        print("  Etat d'index restaure.")

    notes_processed = stats.get("added", 0) + stats.get("updated", 0)
    throughput_notes_per_min = round(notes_processed / (total_s / 60), 1) if total_s > 0 else 0

    print(f"  Total: {total_s}s | notes: {notes_processed} | debit: {throughput_notes_per_min} notes/min")

    return {
        "scenario": "D",
        "total_s": total_s,
        "stats": stats,
        "notes_processed": notes_processed,
        "throughput_notes_per_min": throughput_notes_per_min,
        "throughput_notes_per_hour": round(throughput_notes_per_min * 60, 1),
    }


# ── Rapport ────────────────────────────────────────────────────────────────

def render_markdown_report(results: dict, date_str: str) -> str:
    lines = [
        f"# Rapport Benchmark Baseline — {date_str}",
        "",
        "Generé par `scripts/benchmark_baseline.py`.",
        "",
    ]

    for key in ("A", "B", "C"):
        r = results.get(key)
        if not r:
            continue
        label_map = {"A": "Chat court", "B": "Chat long", "C": "Retrieval pur"}
        lines += [
            f"## Scenario {key} — {label_map[key]}",
            "",
            f"- Requetes: {r['queries']} | Runs: {r['runs']} | Executions: {r['total_executions']} | Erreurs: {r.get('errors', 0)}",
            "",
        ]
        stats = r["stats"]
        headers = ["Metrique", "P50", "P95", "P99", "Min", "Max", "Moyenne"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        metric_labels = {
            "total_s": "Latence totale (s)",
            "retrieval_s": "Retrieval (s)",
            "generation_s": "Generation LLM (s)",
            "chunks_returned": "Chunks retournes",
        }
        for metric, label in metric_labels.items():
            if metric not in stats:
                continue
            s = stats[metric]
            if s["p50"] is None:
                continue
            lines.append(
                f"| {label} | {s['p50']} | {s['p95']} | {s['p99']} | {s['min']} | {s['max']} | {s['mean']} |"
            )
        lines.append("")

    r_d = results.get("D")
    if r_d:
        lines += [
            "## Scenario D — Reindexation complete",
            "",
            f"- Duree totale: **{r_d['total_s']} s**",
            f"- Notes traitees: {r_d['notes_processed']}",
            f"- Debit: **{r_d['throughput_notes_per_min']} notes/min** ({r_d['throughput_notes_per_hour']} notes/h)",
            f"- Stats indexeur: {r_d['stats']}",
            "",
        ]

    lines += [
        "## Comparaison avec les budgets cibles",
        "",
        "| Metrique | Budget P95 cible | Mesure P95 | Delta | Statut |",
        "| --- | --- | --- | --- | --- |",
    ]

    def delta_status(budget: float, measured: float | None) -> tuple[str, str]:
        if measured is None:
            return "N/A", "-"
        delta = round((measured - budget) / budget * 100, 1)
        delta_str = f"{'+' if delta >= 0 else ''}{delta}%"
        if delta > 20:
            return delta_str, "ROUGE"
        if delta > 10:
            return delta_str, "ORANGE"
        return delta_str, "OK"

    budgets = {
        "Chat court — total (s)": (30.0, results.get("A", {}).get("stats", {}).get("total_s", {}).get("p95")),
        "Chat long — total (s)": (60.0, results.get("B", {}).get("stats", {}).get("total_s", {}).get("p95")),
        "Retrieval seul (s)": (8.0, results.get("C", {}).get("stats", {}).get("retrieval_s", {}).get("p95")),
    }
    for label, (budget, measured) in budgets.items():
        delta_str, status = delta_status(budget, measured)
        m_str = str(measured) if measured is not None else "N/A"
        lines.append(f"| {label} | {budget} s | {m_str} s | {delta_str} | {status} |")

    lines.append("")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark baseline ObsiRAG")
    parser.add_argument(
        "--scenario", default="all", choices=["A", "B", "C", "D", "all"],
        help="Scenario a lancer (defaut: all)"
    )
    parser.add_argument(
        "--runs", type=int, default=1,
        help="Nombre de runs par scenario chat (defaut: 1, 3 pour baseline stable)"
    )
    args = parser.parse_args()

    scenarios_to_run = ["A", "B", "C", "D"] if args.scenario == "all" else [args.scenario]

    print("=" * 60)
    print("ObsiRAG — Benchmark Baseline")
    print(f"Scenarios: {', '.join(scenarios_to_run)} | Runs: {args.runs}")
    print("=" * 60)

    # ── Initialisation minimale (sans threads de fond) ──────────────────
    print("\n[init] Chargement ChromaDB...")
    from src.database.chroma_store import ChromaStore
    chroma = ChromaStore()

    rag = None
    if any(s in scenarios_to_run for s in ("A", "B", "C")):
        print("[init] Chargement modele MLX (peut prendre 30-60s)...")
        from src.ai.mlx_client import MlxClient
        from src.ai.rag import RAGPipeline
        from src.metrics import MetricsRecorder
        llm = MlxClient()
        llm.load()
        metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "benchmark_metrics.json")
        rag = RAGPipeline(chroma, llm, metrics=metrics)
        print("[init] RAG pret.")

    indexer = None
    if "D" in scenarios_to_run:
        from src.indexer.pipeline import IndexingPipeline
        indexer = IndexingPipeline(chroma)

    # ── Execution ────────────────────────────────────────────────────────
    results: dict = {}

    if "A" in scenarios_to_run and rag:
        results["A"] = scenario_chat(rag, QUERIES_SHORT, label="A", runs=args.runs)

    if "B" in scenarios_to_run and rag:
        results["B"] = scenario_chat(rag, QUERIES_LONG, label="B", runs=args.runs)

    if "C" in scenarios_to_run and rag:
        results["C"] = scenario_retrieval_only(rag, QUERIES_SHORT, runs=max(args.runs, 3))

    if "D" in scenarios_to_run and indexer:
        results["D"] = scenario_reindexation(indexer)

    # ── Sortie ───────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    output: dict = {
        "generated_at": now.isoformat(),
        "scenarios": scenarios_to_run,
        "runs": args.runs,
        "results": results,
    }

    out_dir = ROOT / "logs" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"benchmark_{date_str}.json"
    md_path = out_dir / f"benchmark_{date_str}.md"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    md_content = render_markdown_report(results, date_str)
    md_path.write_text(md_content, encoding="utf-8")

    # Pointeurs stables
    (out_dir / "benchmark_latest.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "benchmark_latest.md").write_text(md_content, encoding="utf-8")

    print("\n" + "=" * 60)
    print("Rapport genere:")
    print(f"  JSON : {json_path}")
    print(f"  MD   : {md_path}")
    print("=" * 60)
    print(md_content)


if __name__ == "__main__":
    main()
