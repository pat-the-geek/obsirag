from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"

_STEP_SNIPPETS = {
    "embed": """
from src.database.chroma_store import _build_embedding_function
fn = _build_embedding_function()
vec = fn([\"test ping\"])
print(json.dumps({\"vector_count\": len(vec), \"vector_dim\": len(vec[0]) if vec else 0}))
""",
    "chroma_init": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
print(json.dumps({\"collection_ready\": True, \"persist_dir\": store._persist_dir}))
""",
    "chroma_count_api": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
print(json.dumps({\"count\": store._run_collection_op(\"count\")}))
""",
    "sqlite_count": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
print(json.dumps({\"count\": store.count()}))
""",
    "sqlite_list_notes": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
notes = store.list_notes()
print(json.dumps({\"note_count\": len(notes), \"sample\": notes[:2]}, ensure_ascii=False))
""",
    "chroma_peek": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._run_collection_op(\"peek\", limit=1)
print(json.dumps({\"ids\": raw.get(\"ids\", [])[:1], \"keys\": sorted(raw.keys())}, ensure_ascii=False))
""",
    "chroma_get_limit_only": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._collection_get(limit=1)
print(json.dumps({\"ids\": raw.get(\"ids\", [])[:1], \"keys\": sorted(raw.keys())}, ensure_ascii=False))
""",
    "chroma_get_metadatas": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._collection_get(include=[\"metadatas\"], limit=1)
print(json.dumps({\"ids\": raw.get(\"ids\", [])[:1], \"meta_count\": len(raw.get(\"metadatas\") or [])}, ensure_ascii=False))
""",
    "chroma_get_documents": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._collection_get(include=[\"documents\"], limit=1)
print(json.dumps({\"ids\": raw.get(\"ids\", [])[:1], \"doc_count\": len(raw.get(\"documents\") or [])}, ensure_ascii=False))
""",
    "chroma_get_where": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._collection_get(where={\"note_title\": {\"$eq\": \"Artemis II\"}}, include=[\"metadatas\"], limit=1)
print(json.dumps({\"ids\": raw.get(\"ids\", [])[:1], \"meta_count\": len(raw.get(\"metadatas\") or [])}, ensure_ascii=False))
""",
    "chroma_query_base": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._run_collection_op(\"query\", query_texts=[\"Artemis II\"], n_results=1)
print(json.dumps({\"keys\": sorted(raw.keys()), \"id_count\": len((raw.get(\"ids\") or [[]])[0]) if raw.get(\"ids\") else 0}, ensure_ascii=False))
""",
    "chroma_query_metadatas": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._run_collection_op(\"query\", query_texts=[\"Artemis II\"], n_results=1, include=[\"metadatas\"])
print(json.dumps({\"keys\": sorted(raw.keys()), \"meta_count\": len((raw.get(\"metadatas\") or [[]])[0]) if raw.get(\"metadatas\") else 0}, ensure_ascii=False))
""",
    "chroma_query_documents": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._run_collection_op(\"query\", query_texts=[\"Artemis II\"], n_results=1, include=[\"documents\"])
print(json.dumps({\"keys\": sorted(raw.keys()), \"doc_count\": len((raw.get(\"documents\") or [[]])[0]) if raw.get(\"documents\") else 0}, ensure_ascii=False))
""",
    "chroma_query_distances": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
raw = store._run_collection_op(\"query\", query_texts=[\"Artemis II\"], n_results=1, include=[\"distances\"])
print(json.dumps({\"keys\": sorted(raw.keys()), \"distance_count\": len((raw.get(\"distances\") or [[]])[0]) if raw.get(\"distances\") else 0}, ensure_ascii=False))
""",
    "search_keyword": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
result = store.search_by_keyword(\"test\", top_k=3)
print(json.dumps({\"result_count\": len(result), \"sample\": result[:1]}, ensure_ascii=False))
""",
    "search_title": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
result = store.search_by_note_title(\"Artemis II\", top_k=3)
print(json.dumps({\"result_count\": len(result), \"sample\": result[:1]}, ensure_ascii=False))
""",
    "search_semantic": """
from src.database.chroma_store import ChromaStore
store = ChromaStore()
result = store.search(\"Artemis II\", top_k=3)
print(json.dumps({\"result_count\": len(result), \"sample\": result[:1]}, ensure_ascii=False))
""",
}


def _run_child(step: str) -> int:
    sys.path.insert(0, str(ROOT))
    snippet = "import json\n" + _STEP_SNIPPETS[step]
    namespace: dict[str, object] = {}
    exec(snippet, namespace, namespace)
    return 0


def _signal_name(returncode: int) -> str | None:
    if returncode >= 0:
        return None
    try:
        return signal.Signals(-returncode).name
    except ValueError:
        return f"SIG{-returncode}"


def _classify_probe(completed: subprocess.CompletedProcess[str], step: str) -> dict[str, object]:
    result = {
        "step": step,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "").strip(),
        "stderr": (completed.stderr or "").strip(),
    }
    signal_name = _signal_name(completed.returncode)
    if signal_name:
        result["signal"] = signal_name
        result["nativeCrash"] = True
    else:
        result["nativeCrash"] = False
    return result


def _probe_step(step: str) -> dict[str, object]:
    completed = subprocess.run(
        [str(PYTHON), __file__, "--child", step],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    return _classify_probe(completed, step)


def _build_summary(results: list[dict[str, object]]) -> dict[str, object]:
    failing = [item for item in results if int(item["returncode"]) != 0]
    first_failure = failing[0] if failing else None
    first_native = next((item for item in failing if bool(item.get("nativeCrash"))), None)
    return {
        "ok": not failing,
        "stepCount": len(results),
        "firstFailure": None if first_failure is None else {
            "step": first_failure["step"],
            "returncode": first_failure["returncode"],
            "signal": first_failure.get("signal"),
        },
        "firstNativeCrash": None if first_native is None else {
            "step": first_native["step"],
            "returncode": first_native["returncode"],
            "signal": first_native.get("signal"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnostique isolé des crashes Chroma")
    parser.add_argument("--child", choices=sorted(_STEP_SNIPPETS), help="Exécuter une seule étape dans le process courant")
    args = parser.parse_args()

    if args.child:
        return _run_child(args.child)

    results = [_probe_step(step) for step in _STEP_SNIPPETS]
    print(json.dumps({"summary": _build_summary(results), "results": results}, ensure_ascii=False, indent=2))
    return 1 if any(int(item["returncode"]) != 0 for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())