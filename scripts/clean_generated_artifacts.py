#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ai.mlx_client import MlxClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.indexer.pipeline import IndexingPipeline
from src.learning.autolearn import AutoLearner
from src.logger import configure_logging
from src.metrics import MetricsRecorder


def _parse_types(raw: str) -> list[str]:
    allowed = {"insight", "synapse"}
    selected = [item.strip().lower() for item in str(raw or "").split(",") if item.strip()]
    invalid = [item for item in selected if item not in allowed]
    if invalid:
        raise argparse.ArgumentTypeError(f"Types invalides: {', '.join(invalid)}")
    return selected or ["insight", "synapse"]


def _iter_cleanup_paths(selected_types: list[str], *, include_archives: bool) -> list[Path]:
    roots: list[Path] = []
    if "insight" in selected_types:
        roots.append(settings.insights_dir)
    if "synapse" in selected_types:
        roots.append(settings.synapses_dir)

    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if not include_archives and AutoLearner._is_archive_artifact_path(path):
                continue
            paths.append(path)
    return sorted(paths)


def _recent_artifact_paths(chroma: ChromaStore, selected_types: list[str], limit: int) -> list[tuple[str, Path]]:
    results: list[tuple[str, Path]] = []
    for note_type in selected_types:
        try:
            notes = list(chroma.list_notes_by_type(note_type))
        except Exception:
            notes = []
        for note in notes[: max(0, limit)]:
            file_path = str(note.get("file_path", "")).strip()
            if not file_path:
                continue
            path = settings.vault / file_path
            if not path.exists() or AutoLearner._is_archive_artifact_path(path):
                continue
            results.append((note_type, path))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Régénère les artefacts récents et nettoie les insights/synapses contaminés."
    )
    parser.add_argument(
        "--mode",
        choices=["regen-recent", "cleanup", "both"],
        default="both",
        help="Action à exécuter.",
    )
    parser.add_argument(
        "--types",
        type=_parse_types,
        default=["insight", "synapse"],
        help="Types ciblés, séparés par des virgules: insight,synapse",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Nombre d'artefacts récents à régénérer par type.",
    )
    parser.add_argument(
        "--include-archives",
        action="store_true",
        help="Inclut aussi les fichiers archivés dans le nettoyage batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prévisualise sans écrire.",
    )
    args = parser.parse_args()

    configure_logging(settings.log_level, settings.log_dir)
    metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
    chroma = ChromaStore()
    llm = MlxClient()
    rag = RAGPipeline(chroma, llm, metrics=metrics)
    indexer = IndexingPipeline(chroma)
    learner = AutoLearner(chroma, rag, indexer, ui_active_fn=lambda: False, metrics=metrics)

    regen_total = 0
    cleanup_total = 0
    skipped_total = 0

    try:
        llm.load()

        if args.mode in {"regen-recent", "both"}:
            print("Régénération ciblée des artefacts récents…")
            for note_type, path in _recent_artifact_paths(chroma, args.types, args.limit):
                if note_type == "insight":
                    changed = learner._regenerate_insight_artifact(path, dry_run=args.dry_run)
                else:
                    changed = learner._regenerate_synapse_artifact(path, dry_run=args.dry_run)
                if changed:
                    regen_total += 1
                    print(f"  {'[dry-run] ' if args.dry_run else ''}régénéré: {path}")
                else:
                    skipped_total += 1
                    print(f"  ignoré: {path}")

        if args.mode in {"cleanup", "both"}:
            print("Nettoyage batch des artefacts existants…")
            for path in _iter_cleanup_paths(args.types, include_archives=args.include_archives):
                changed = learner._rewrite_generated_artifact_in_french(
                    path,
                    operation="artifact_cleanup",
                    dry_run=args.dry_run,
                )
                if changed:
                    cleanup_total += 1
                    print(f"  {'[dry-run] ' if args.dry_run else ''}nettoyé: {path}")

    finally:
        try:
            llm.unload()
        except Exception:
            pass

    print(
        f"Terminé. Régénérés: {regen_total} | Nettoyés: {cleanup_total} | Ignorés: {skipped_total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())