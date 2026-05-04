from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from src.ai.ollama_client import OllamaClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.logger import configure_logging
from src.metrics import MetricsRecorder
from src.storage.safe_read import read_text_file


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_ROMAN_NUMERAL_RE = re.compile(r"^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)$", re.I)
_LEADING_QUERY_RE = re.compile(
    r"^\s*(?:parle(?:-?\s*)moi|dis(?:-?\s*)moi|explique(?:-?\s*)moi|pr[ée]sente(?:-?\s*)moi|"
    r"raconte(?:-?\s*)moi|que\s+sais[-\s]?tu\s+de|qui\s+est|qu['’]est(?:-?\s*ce\s+que)?|"
    r"d[ée]finis|d[ée]finition\s+de)\s+(?:de|d['’]|du|des|la|le|les|sur\s+)?",
    re.I,
)
_STOP_WORDS = {
    "afin", "alors", "apres", "après", "au", "aux", "aussi", "avec", "avoir",
    "bonjour", "cela", "ceci", "comme", "comment", "contre", "coffre", "dans", "de",
    "depuis", "des", "dire", "dis", "donc", "dont", "du", "elle", "elles", "entre",
    "est", "et", "etre", "être", "faire", "il", "ils", "je", "juste", "la", "le",
    "les", "leur", "leurs", "lors", "lui", "mais", "me", "meme", "même", "mes", "moi",
    "moins", "ne", "nos", "note", "notes", "nous", "ou", "où", "par", "parle", "pas",
    "plus", "pour", "pourquoi", "quand", "que", "quel", "quelle", "quelles", "quels",
    "qui", "quoi", "raconte", "salut", "sans", "sera", "ses", "son", "sont", "sous",
    "sur", "ta", "te", "tes", "toi", "ton", "tout", "tous", "toute", "toutes", "très",
    "tres", "tu", "une", "vos", "votre", "vous",
}


@dataclass(slots=True)
class _NoteRecord:
    path: Path
    rel_path: str
    title: str
    body: str
    date_modified: str
    note_type: str


def _note_type_for_path(file_path: str) -> str:
    normalized = file_path.replace("\\", "/").lower()
    if "/obsirag/web_insights/" in normalized or normalized.startswith("obsirag/web_insights/"):
        return "web_insight"
    if "/obsirag/insights/" in normalized or normalized.startswith("obsirag/insights/"):
        return "insight"
    if "/obsirag/synapses/" in normalized or normalized.startswith("obsirag/synapses/"):
        return "synapse"
    if "/obsirag/synthesis/" in normalized or normalized.startswith("obsirag/synthesis/"):
        return "report"
    return "user"


def _is_generated_chat_artifact(rel_path: str) -> bool:
    normalized = rel_path.replace("\\", "/").lower()
    if not normalized.startswith("obsirag/"):
        return False
    name = Path(normalized).name
    return name.startswith("chat_") or "/obsirag/conversations/" in normalized


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or " ").strip()


def _extract_focus_query(query: str) -> str:
    normalized = _normalize_whitespace(query)
    normalized = _LEADING_QUERY_RE.sub("", normalized)
    return normalized.strip(" ?!.,:;\"'“”‘’") or _normalize_whitespace(query)


def _tokenize_query(query: str) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(query.lower()):
        if token in _STOP_WORDS:
            continue
        if len(token) < 3 and not _ROMAN_NUMERAL_RE.match(token):
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens[:12]


def _parse_note(path: Path) -> tuple[str, str]:
    raw = read_text_file(path, default="", errors="replace")
    if not raw.strip():
        return path.stem, ""
    try:
        post = frontmatter.loads(raw)
        title = str(post.metadata.get("title") or path.stem)
        body = str(post.content or "")
        return title, body
    except Exception:
        return path.stem, raw


def _iter_note_records() -> list[_NoteRecord]:
    vault = settings.vault
    if not vault.exists():
        return []

    records: list[_NoteRecord] = []
    for path in vault.rglob("*.md"):
        rel_path = path.relative_to(vault).as_posix()
        normalized = rel_path.lower()
        if normalized.startswith(".obsidian/"):
            continue
        if _is_generated_chat_artifact(rel_path):
            continue
        try:
            if path.stat().st_size > settings.max_note_size_bytes:
                continue
            date_modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        except Exception:
            date_modified = ""
        title, body = _parse_note(path)
        if not body.strip():
            continue
        records.append(
            _NoteRecord(
                path=path,
                rel_path=rel_path,
                title=title,
                body=body,
                date_modified=date_modified,
                note_type=_note_type_for_path(rel_path),
            )
        )
    return records


def _path_bias(record: _NoteRecord) -> int:
    if record.note_type == "user":
        return 10
    if record.note_type == "web_insight":
        return 7
    if record.note_type == "report":
        return 3
    if record.note_type == "synapse":
        return 1
    if record.note_type == "insight":
        return -2
    return 0


def _snippet_score(text: str, terms: list[str], focus_query: str) -> tuple[int, int]:
    lowered = text.lower()
    exact_phrase = 1 if focus_query and focus_query in lowered else 0
    matched_terms = sum(1 for term in terms if term in lowered)
    weighted_hits = sum(min(lowered.count(term), 4) for term in terms)
    return exact_phrase * 10 + matched_terms * 4 + weighted_hits, matched_terms


def _select_excerpt(body: str, terms: list[str], focus_query: str, max_chars: int = 700) -> str:
    paragraphs = [
        _normalize_whitespace(paragraph)
        for paragraph in re.split(r"\n\s*\n+", body)
        if _normalize_whitespace(paragraph)
    ]
    if not paragraphs:
        return ""

    ranked = sorted(
        paragraphs,
        key=lambda paragraph: (_snippet_score(paragraph, terms, focus_query), -len(paragraph)),
        reverse=True,
    )
    selected: list[str] = []
    budget = max_chars
    for paragraph in ranked[:2]:
        paragraph_score, matched_terms = _snippet_score(paragraph, terms, focus_query)
        if paragraph_score <= 0 and matched_terms == 0:
            continue
        if budget <= 0:
            break
        chunk = paragraph[:budget]
        if len(paragraph) > budget:
            chunk += "…"
        selected.append(chunk)
        budget -= len(chunk)
    if selected:
        return "\n\n".join(selected).strip()
    return paragraphs[0][:max_chars]


def _rank_note(record: _NoteRecord, terms: list[str], focus_query: str) -> tuple[int, int, int]:
    title_l = record.title.lower()
    body_l = record.body.lower()
    path_l = record.rel_path.lower()

    exact_phrase_hits = 0
    coverage = 0
    score = _path_bias(record)

    if focus_query and focus_query in title_l:
        score += 28
        exact_phrase_hits += 1
    if focus_query and focus_query in body_l:
        score += 16
        exact_phrase_hits += 1

    for term in terms:
        term_hits = 0
        if term in title_l:
            score += 12
            term_hits += 1
        if term in path_l:
            score += 5
            term_hits += 1
        occurrences = body_l.count(term)
        if occurrences:
            score += min(occurrences, 6) * 2
            term_hits += 1
        if term_hits:
            coverage += 1

    if record.note_type == "insight" and coverage < 2 and exact_phrase_hits == 0:
        score -= 12
    return score, coverage, exact_phrase_hits


def _record_to_chunk(record: _NoteRecord, query: str, *, is_primary: bool) -> dict[str, Any] | None:
    focus_query = _extract_focus_query(query).lower()
    terms = _tokenize_query(focus_query)
    excerpt = _select_excerpt(record.body, terms, focus_query)
    if not excerpt:
        return None
    score, coverage, exact_phrase_hits = _rank_note(record, terms, focus_query)
    return {
        "chunk_id": f"fallback_{record.rel_path.replace('/', '_')}",
        "text": excerpt,
        "metadata": {
            "file_path": record.rel_path,
            "note_title": record.title,
            "date_modified": record.date_modified,
            "section_title": "",
            "wikilinks": "",
            "is_primary": is_primary,
            "note_type": record.note_type,
            "primary_note_key_hint": record.rel_path if is_primary else "",
            "fallback_coverage": coverage,
            "fallback_exact_phrase_hits": exact_phrase_hits,
        },
        "score": min(max(score, 0) / 40.0, 1.0),
    }


class _FallbackChroma:
    def __init__(self, records: list[_NoteRecord]) -> None:
        self._records = records

    def _filter_records(self, where: dict[str, Any] | None) -> list[_NoteRecord]:
        if not where:
            return list(self._records)
        filtered = list(self._records)
        for field, condition in where.items():
            if isinstance(condition, dict) and "$eq" in condition:
                value = str(condition["$eq"])
            else:
                value = str(condition)
            if field == "file_path":
                filtered = [record for record in filtered if record.rel_path == value]
            elif field == "note_title":
                filtered = [record for record in filtered if record.title == value]
        return filtered

    def search(self, query: str, top_k: int = 8, where: dict | None = None) -> list[dict[str, Any]]:
        focus_query = _extract_focus_query(query).lower()
        terms = _tokenize_query(focus_query)
        if not terms and focus_query:
            terms = [focus_query]

        ranked: list[tuple[tuple[int, int, int], _NoteRecord]] = []
        for record in self._filter_records(where):
            score = _rank_note(record, terms, focus_query)
            if score[0] <= 0:
                continue
            ranked.append((score, record))

        ranked.sort(key=lambda item: (item[0][0], item[0][1], item[0][2], item[1].date_modified), reverse=True)
        chunks: list[dict[str, Any]] = []
        for index, (_score, record) in enumerate(ranked[:max(1, top_k)]):
            chunk = _record_to_chunk(record, query, is_primary=index == 0)
            if chunk is not None:
                chunks.append(chunk)
        return chunks

    def get_chunks_by_note_title(self, note_title: str, limit: int = 2) -> list[dict[str, Any]]:
        return self.search(note_title, top_k=limit, where={"note_title": note_title})

    def get_chunks_by_file_path(self, file_path: str, limit: int = 2) -> list[dict[str, Any]]:
        return self.search(file_path, top_k=limit, where={"file_path": file_path})

    def get_chunks_by_file_paths(self, file_paths: list[str], limit_per_path: int = 2) -> dict[str, list[dict[str, Any]]]:
        return {
            file_path: self.get_chunks_by_file_path(file_path, limit=limit_per_path)
            for file_path in file_paths
        }


def _build_runtime(records: list[_NoteRecord]) -> tuple[OllamaClient, RAGPipeline]:
    configure_logging(settings.log_level, settings.log_dir)
    metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
    llm = OllamaClient()
    rag = RAGPipeline(_FallbackChroma(records), llm, metrics=metrics)
    return llm, rag


def main() -> int:
    payload = json.load(sys.stdin)
    prompt = str(payload.get("prompt") or "").strip()
    history = list(payload.get("history") or [])
    if not prompt:
        raise SystemExit("Missing prompt")

    records = _iter_note_records()
    llm, rag = _build_runtime(records)
    try:
        resolved_query = rag._resolve_query_with_history(prompt, history)
        chunks = rag._chroma.search(resolved_query, top_k=4)
        if not chunks:
            sys.stdout.write(
                json.dumps(
                    {
                        "answer": "Cette information n'est pas dans ton coffre.",
                        "sources": [],
                        "fallbackMode": "filesystem",
                    },
                    ensure_ascii=False,
                )
            )
            sys.stdout.flush()
            return 0

        intent = "synthesis" if rag._synthesis_patterns.search(resolved_query) else "general_kw_fallback"
        context = rag._build_context(chunks, resolved_query, intent)
        messages = rag._build_messages(
            prompt,
            context,
            history,
            intent=intent,
            resolved_query=resolved_query,
        )
        llm.load()
        answer = rag._run_chat_attempt(messages, context, history, resolved_query, intent)
        sys.stdout.write(
            json.dumps(
                {
                    "answer": answer,
                    "sources": chunks,
                    "fallbackMode": "filesystem",
                },
                ensure_ascii=False,
            )
        )
        sys.stdout.flush()
        return 0
    finally:
        try:
            llm.unload()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())