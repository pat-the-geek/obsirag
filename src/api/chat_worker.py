from __future__ import annotations

import json
import sys
from typing import Any

from src.ai.mlx_client import MlxClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database.chroma_store import ChromaStore
from src.logger import configure_logging
from src.metrics import MetricsRecorder


def _build_runtime() -> tuple[MlxClient, RAGPipeline]:
    configure_logging(settings.log_level, settings.log_dir)
    metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
    chroma = ChromaStore()
    llm = MlxClient()
    rag = RAGPipeline(chroma, llm, metrics=metrics)
    return llm, rag


def main() -> int:
    payload = json.load(sys.stdin)
    prompt = str(payload.get("prompt") or "").strip()
    history = list(payload.get("history") or [])
    if not prompt:
        raise SystemExit("Missing prompt")

    llm, rag = _build_runtime()
    try:
        llm.load()
        answer, sources = rag.query(prompt, chat_history=history)
        sys.stdout.write(json.dumps({"answer": answer, "sources": sources}, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    finally:
        try:
            llm.unload()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())