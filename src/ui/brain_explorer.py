from __future__ import annotations

from datetime import datetime, timedelta

from src.ui.note_badges import get_note_type


def filter_brain_notes(
    notes: list[dict],
    selected_folders: list[str],
    selected_tags: list[str],
    selected_types: list[str] | None = None,
    search_text: str = "",
    modified_within_days: int | None = None,
    now: datetime | None = None,
) -> list[dict]:
    filtered = list(notes)

    if selected_folders and "Tous" not in selected_folders:
        folder_set = set(selected_folders)
        filtered = [
            note for note in filtered
            if note.get("folder") in folder_set
        ]

    if selected_tags:
        tag_set = {tag.lower() for tag in selected_tags}
        filtered = [
            note for note in filtered
            if tag_set & {tag.lower() for tag in note.get("tags", [])}
        ]

    if selected_types and "Tous" not in selected_types:
        type_set = {note_type.lower() for note_type in selected_types}
        filtered = [
            note for note in filtered
            if get_note_type(note.get("file_path", "")) in type_set
        ]

    search = search_text.strip().lower()
    if search:
        filtered = [
            note for note in filtered
            if search in (note.get("title") or "").lower()
            or search in (note.get("file_path") or "").lower()
            or any(search in tag.lower() for tag in note.get("tags", []))
        ]

    if modified_within_days:
        reference = now or datetime.now()
        threshold = reference - timedelta(days=modified_within_days)
        recent: list[dict] = []
        for note in filtered:
            modified = _parse_note_date(note.get("date_modified", ""))
            if modified and modified >= threshold:
                recent.append(note)
        filtered = recent

    return filtered


def build_recent_notes(notes: list[dict], limit: int = 8) -> list[dict]:
    return sorted(
        notes,
        key=lambda note: (_parse_note_date(note.get("date_modified", "")) or datetime.min),
        reverse=True,
    )[:limit]


def build_centrality_spotlight(notes: list[dict], top_connected: list[dict], limit: int = 6) -> list[dict]:
    by_path = {note.get("file_path"): note for note in notes}
    spotlight: list[dict] = []

    for item in top_connected[:limit]:
        file_path = item.get("file_path")
        note = by_path.get(file_path)
        if not note:
            continue
        spotlight.append({
            "file_path": file_path,
            "title": note.get("title") or file_path,
            "score": item.get("score", 0),
            "date_modified": note.get("date_modified", "")[:10],
            "tags": note.get("tags", []),
        })

    return spotlight


def build_folder_summary(notes: list[dict], limit: int = 6) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for note in notes:
        folder = note.get("folder") or "(racine)"
        counts[folder] = counts.get(folder, 0) + 1
    return [
        {"folder": folder, "count": count}
        for folder, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def build_tag_summary(notes: list[dict], limit: int = 10) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for note in notes:
        for tag in note.get("tags", []):
            if not tag:
                continue
            counts[tag] = counts.get(tag, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def build_type_summary(notes: list[dict]) -> list[dict[str, int | str]]:
    counts: dict[str, int] = {}
    for note in notes:
        note_type = get_note_type(note.get("file_path", ""))
        counts[note_type] = counts.get(note_type, 0) + 1
    return [
        {"type": note_type, "count": count}
        for note_type, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _parse_note_date(value: str) -> datetime | None:
    if not value:
        return None
    for candidate in (value, value.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is not None:
                return parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None