"""
Worker DDG autonome — exécuté comme sous-processus pour éviter le blocage
du GIL par primp (Rust/Tokio) dans le process uvicorn principal.

N'importe QUE ddgs — pas de stack ObsiRAG — pour démarrer vite.

Usage:
    python src/ai/ddg_worker.py <query> [max_results]

Sortie: JSON array sur stdout.
"""
import json
import re
import sys


_STOPWORDS = {
    "que", "qui", "quoi", "quels", "quelles", "quel", "quelle",
    "est", "sont", "les", "des", "une", "aux", "sur", "par", "pour",
    "dans", "avec", "vers", "la", "le", "du", "de", "un", "en", "et",
    "ou", "ne", "pas", "plus", "se", "sa", "son", "ses", "me", "ce",
    "what", "which", "where", "when", "who", "how", "the", "is", "are",
    "of", "in", "on", "at", "to", "for", "and", "or",
}


def _is_latin(text: str) -> bool:
    if not text:
        return False
    latin = sum(1 for c in text if c.isalpha() and ord(c) < 0x500)
    total = sum(1 for c in text if c.isalpha())
    return total == 0 or latin / total >= 0.7


def _keywordize(text: str) -> str:
    tokens = [t for t in re.findall(r"[A-Za-zÀ-ÿ0-9-]+", text)
              if len(t) >= 3 and t.lower() not in _STOPWORDS]
    return " ".join(tokens[:6]) if tokens else text


def run(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS  # only import once process is started
    kw = _keywordize(query)
    candidates = [kw]
    # add quoted subject phrase variant
    words = kw.split()
    if len(words) >= 2:
        candidates.append(f'"{" ".join(words[:3])}"')
    candidates.append(f"{kw} -知乎")

    best: list[dict] = []
    for cq in candidates:
        try:
            with DDGS(timeout=8, verify=False) as ddgs:
                raw = list(ddgs.text(cq, region="fr-fr", safesearch="off", max_results=max_results + 3))
            filtered = [r for r in raw if _is_latin(r.get("title", "")) and _is_latin(r.get("body", ""))][:max_results]
            if len(filtered) > len(best):
                best = filtered
        except Exception:
            continue
    return best


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("[]")
        sys.exit(0)
    _query = sys.argv[1]
    _max = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    try:
        results = run(_query, _max)
        print(json.dumps(results, ensure_ascii=False))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("[]")
    sys.exit(0)
