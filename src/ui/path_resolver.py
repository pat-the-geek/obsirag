from __future__ import annotations

from pathlib import Path, PurePath

from src.config import settings


def normalize_vault_relative_path(path_str: str, vault_root: Path | None = None) -> str:
    normalized = _normalize_path_string(path_str)
    if not normalized:
        return ""

    resolved = resolve_vault_path(normalized, vault_root=vault_root)
    root = vault_root or settings.vault
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return Path(normalized).as_posix() if Path(normalized).is_absolute() else PurePath(normalized).as_posix()


def resolve_vault_path(path_str: str, vault_root: Path | None = None) -> Path:
    normalized = _normalize_path_string(path_str)
    root = vault_root or settings.vault
    if not normalized:
        return root

    path = Path(normalized)
    if path.is_absolute():
        if path.exists():
            return path
        rebased = _rebase_absolute_path_to_vault(path, root)
        return rebased or path

    return root / PurePath(normalized)


def _normalize_path_string(path_str: str) -> str:
    normalized = str(path_str or "").strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _rebase_absolute_path_to_vault(path: Path, vault_root: Path) -> Path | None:
    parts = path.parts
    for start in range(1, len(parts)):
        suffix = Path(*parts[start:])
        candidate = vault_root / suffix
        if candidate.exists():
            return candidate
    return None