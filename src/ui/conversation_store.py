from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.storage.safe_read import read_text_lines


def list_saved_conversation_entries(
    root: Path,
    *,
    limit: int = 12,
    vault_root: Path | None = None,
    title_loader: Callable[[Path], str] | None = None,
) -> list[dict[str, str]]:
    if not root.exists():
        return []

    entries: list[dict[str, str]] = []
    path_root = vault_root or root.parent
    title_fn = title_loader or _read_first_heading

    for path in _iter_conversation_markdown_files(root):
        entries.append(
            {
                "title": title_fn(path) or path.stem.replace("-", " "),
                "file_path": str(path.relative_to(path_root)),
                "absolute_path": str(path),
                "month": path.parent.name,
            }
        )
        if len(entries) >= max(0, int(limit)):
            break

    return entries


def _iter_conversation_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for month_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        files.extend(month_dir.glob("*.md"))
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _read_first_heading(path: Path) -> str:
    try:
        for line in read_text_lines(path, default=[], errors="replace"):
            if line.startswith("# "):
                return line[2:].strip()
    except OSError:
        return ""
    return ""