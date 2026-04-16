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

from scripts.benchmark_perf11_mlx_generation import InstrumentedMlxClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.metrics import MetricsRecorder


DEFAULT_MODELS = [
    "mlx-community/Qwen2.5-7B-Instruct-4bit",
    "google/gemma-4-e4b",
    "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit",
]

DEFAULT_PROMPTS = [
    "Quelles notes mentionnent des idées clés dans mon coffre ?",
    "Fais une synthèse complète de mes apprentissages majeurs.",
    "Quels liens peux-tu faire entre mes différentes notes sur la technique et l'apprentissage ?",
]

DEFAULT_WARMUP = "Donne-moi un aperçu global de mon coffre sans entrer dans le détail."


def _safe_slug(value: str) -> str:
    return value.replace("/", "__").replace(":", "_")


def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 3) if values else 0.0


def _mean_tokens(values: list[int]) -> float:
    return round(statistics.mean(values), 1) if values else 0.0


def run_model(model_name: str, prompts: list[str], warmup_prompt: str, preview_chars: int) -> dict:
    settings.mlx_chat_model = model_name
    llm = InstrumentedMlxClient()
    chroma = ChromaStore()
    metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / f"bench_shortlist_{_safe_slug(model_name)}.json")
    rag = RAGPipeline(chroma, llm, metrics)

    results: list[dict] = []
    warmup_total_s = 0.0
    load_total_s = 0.0
    error_message: str | None = None

    try:
        try:
            t_load = time.perf_counter()
            llm.load()
            load_total_s = round(time.perf_counter() - t_load, 3)

            t_warm = time.perf_counter()
            warm_stream, _ = rag.query_stream(warmup_prompt, chat_history=[])
            _ = "".join(warm_stream)
            warmup_total_s = round(time.perf_counter() - t_warm, 3)

            for prompt in prompts:
                started = time.perf_counter()
                stream, sources = rag.query_stream(prompt, chat_history=[])
                answer = "".join(stream)
                total_s = round(time.perf_counter() - started, 3)
                results.append(
                    {
                        "prompt": prompt,
                        "ttft_s": round(llm._last_ttft_s, 3),
                        "tps": round(llm._last_tps, 2),
                        "total_s": total_s,
                        "tokens": llm._last_tokens,
                        "sources": len(sources),
                        "answer_preview": answer[:preview_chars],
                    }
                )
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
    finally:
        llm.unload()

    return {
        "model": model_name,
        "error": error_message,
        "load_total_s": load_total_s,
        "warmup_total_s": warmup_total_s,
        "avg_ttft_s": _mean([item["ttft_s"] for item in results]),
        "avg_tps": round(statistics.mean([item["tps"] for item in results]), 2) if results else 0.0,
        "avg_total_s": _mean([item["total_s"] for item in results]),
        "avg_tokens": _mean_tokens([item["tokens"] for item in results]),
        "results": results,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# Benchmark court de modèles MLX",
        "",
        f"Généré le {payload['generated_at']}",
        "",
        "## Résumé",
        "",
        "| Modèle | Chargement | Warm-up | TTFT moyen | Débit moyen | Temps total moyen | Tokens moyens |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for result in payload["results"]:
        if result.get("error"):
            lines.append(
                f"| `{result['model']}` | {result['load_total_s']} s | {result['warmup_total_s']} s | "
                f"- | - | - | erreur: {result['error']} |"
            )
        else:
            lines.append(
                f"| `{result['model']}` | {result['load_total_s']} s | {result['warmup_total_s']} s | "
                f"{result['avg_ttft_s']} s | {result['avg_tps']} tok/s | {result['avg_total_s']} s | {result['avg_tokens']} |"
            )

    lines.extend([
        "",
        "## Détail par prompt",
    ])

    for result in payload["results"]:
        lines.extend([
            "",
            f"### {result['model']}",
            "",
        ])
        if result.get("error"):
            lines.extend([
                f"Erreur: {result['error']}",
            ])
            continue
        lines.extend([
            "| Prompt | TTFT | Débit | Total | Tokens | Sources | Extrait |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for item in result["results"]:
            excerpt = item["answer_preview"].replace("\n", " ").replace("|", "/")
            lines.append(
                f"| {item['prompt']} | {item['ttft_s']} s | {item['tps']} tok/s | {item['total_s']} s | "
                f"{item['tokens']} | {item['sources']} | {excerpt} |"
            )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark court de modèles MLX pour ObsiRAG")
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Modèle MLX à tester. Répéter l'option pour plusieurs modèles.",
    )
    parser.add_argument(
        "--prompt",
        dest="prompts",
        action="append",
        help="Prompt à mesurer. Répéter l'option pour plusieurs prompts.",
    )
    parser.add_argument(
        "--warmup-prompt",
        default=DEFAULT_WARMUP,
        help="Prompt d'échauffement exécuté avant les mesures.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=240,
        help="Nombre de caractères conservés dans l'extrait de réponse.",
    )
    parser.add_argument(
        "--output-prefix",
        default="benchmark_model_shortlist",
        help="Préfixe des fichiers de sortie sous logs/validation.",
    )
    args = parser.parse_args()

    models = args.models or DEFAULT_MODELS
    prompts = args.prompts or DEFAULT_PROMPTS

    print("=" * 60)
    print("Benchmark court de modèles MLX")
    print(f"Modèles: {len(models)} | Prompts: {len(prompts)}")
    print("=" * 60)

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "warmup_prompt": args.warmup_prompt,
        "prompts": prompts,
        "results": [],
    }

    for model_name in models:
        print(f"\n[model] {model_name}")
        result = run_model(model_name, prompts, args.warmup_prompt, args.preview_chars)
        payload["results"].append(result)
        if result.get("error"):
            print(
                f"  load={result['load_total_s']}s warmup={result['warmup_total_s']}s "
                f"ERREUR={result['error']}"
            )
        else:
            print(
                f"  load={result['load_total_s']}s warmup={result['warmup_total_s']}s "
                f"ttft={result['avg_ttft_s']}s tps={result['avg_tps']} total={result['avg_total_s']}s"
            )

    out_dir = ROOT / "logs" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = args.output_prefix
    json_path = out_dir / f"{prefix}.json"
    md_path = out_dir / f"{prefix}.md"
    latest_json_path = out_dir / f"{prefix}_latest.json"
    latest_md_path = out_dir / f"{prefix}_latest.md"

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    md_text = render_markdown(payload)

    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")
    latest_json_path.write_text(json_text, encoding="utf-8")
    latest_md_path.write_text(md_text, encoding="utf-8")

    print("\nRapports générés:")
    print(f"  JSON: {json_path}")
    print(f"  MD  : {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())