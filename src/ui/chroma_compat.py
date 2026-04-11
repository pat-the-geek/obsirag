from __future__ import annotations

from pathlib import Path


def list_notes_sorted_by_title(chroma) -> list[dict]:
    helper = getattr(chroma, "list_notes_sorted_by_title", None)
    if callable(helper):
        return helper()
    return sorted(
        chroma.list_notes(),
        key=lambda note: str(note.get("title") or Path(note["file_path"]).stem).lower(),
    )


def list_recent_notes(chroma, limit: int = 20) -> list[dict]:
    helper = getattr(chroma, "list_recent_notes", None)
    if callable(helper):
        return helper(limit=limit)

    notes = sorted(
        chroma.list_notes(),
        key=lambda note: str(note.get("date_modified") or ""),
        reverse=True,
    )
    notes = sorted(notes, key=lambda note: not bool(note.get("date_modified")))
    return notes[:limit] if limit > 0 else notes


def get_backlinks(chroma, file_path: str) -> list[dict]:
    helper = getattr(chroma, "get_backlinks", None)
    if callable(helper):
        return helper(file_path)

    target_name = Path(file_path).stem.lower()
    return [
        note for note in chroma.list_notes()
        if note["file_path"] != file_path
        and target_name in [wikilink.lower() for wikilink in note.get("wikilinks", [])]
    ]