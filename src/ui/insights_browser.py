from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable


def build_artifact_entries(notes: list[dict]) -> list[tuple[str, float]]:
    entries: list[tuple[str, float]] = []
    seen_paths: set[str] = set()

    for note in notes:
        path_str = str(note.get("file_path") or "")
        if not path_str or path_str in seen_paths:
            continue
        seen_paths.add(path_str)
        entries.append((path_str, _parse_note_timestamp(note.get("date_modified", ""))))

    entries.sort(key=lambda item: item[1], reverse=True)
    return entries


def build_artifact_expander_label(path_str: str, mtime: float, icon: str) -> str:
    stem = Path(path_str).stem
    if mtime > 0:
        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    else:
        date_str = "date inconnue"
    return f"{icon} {stem} — {date_str}"


def build_artifact_panel_caption(filtered_count: int, total_count: int, label: str, obsidian_subpath: str) -> str:
    return (
        f"{filtered_count} / {total_count} {label} · "
        f"Visibles dans Obsidian sous `{obsidian_subpath}`"
    )


def build_month_options(entries: list[tuple[str, float]]) -> list[str]:
    months = {
        datetime.fromtimestamp(mtime).strftime("%Y-%m")
        for _path, mtime in entries
        if mtime > 0
    }
    return ["Tous"] + sorted(months, reverse=True)


def filter_markdown_entries(
    entries: list[tuple[str, float]],
    *,
    search_text: str = "",
    month_filter: str = "Tous",
    content_lookup: Callable[[str, float], str] | None = None,
) -> list[tuple[str, float]]:
    search = search_text.strip().lower()
    filtered: list[tuple[str, float]] = []

    for path_str, mtime in entries:
        month = datetime.fromtimestamp(mtime).strftime("%Y-%m")
        if month_filter != "Tous" and month != month_filter:
            continue

        if search:
            path = Path(path_str)
            haystacks = [path.stem.lower(), path.name.lower(), str(path).lower()]
            if content_lookup is not None:
                haystacks.append(content_lookup(path_str, mtime).lower())
            if not any(search in haystack for haystack in haystacks):
                continue

        filtered.append((path_str, mtime))

    return filtered


def load_query_history(lines: list[str]) -> list[dict]:
    queries: list[dict] = []
    for line in lines:
        try:
            queries.append(json.loads(line))
        except Exception:
            continue
    queries.sort(key=lambda item: item.get("ts", ""), reverse=True)
    return queries


def build_query_day_options(queries: list[dict]) -> list[str]:
    days = {query.get("ts", "")[:10] for query in queries if query.get("ts")}
    return ["Toutes"] + sorted(days, reverse=True)


def filter_queries(
    queries: list[dict],
    *,
    search_text: str = "",
    day_filter: str = "Toutes",
) -> list[dict]:
    search = search_text.strip().lower()
    filtered: list[dict] = []

    for query in queries:
        ts = query.get("ts", "")
        if day_filter != "Toutes" and not ts.startswith(day_filter):
            continue
        if search and search not in query.get("query", "").lower():
            continue
        filtered.append(query)

    return filtered


def _parse_note_timestamp(value: str) -> float:
    if not value:
        return 0.0
    for candidate in (value, value.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate).timestamp()
        except ValueError:
            continue
    return 0.0