"""
Patch les notes d'entités existantes en ajoutant un lien image wudd.ai
pour les notes qui n'en ont pas encore.

Usage : python scripts/patch_entity_images.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

# Permet d'importer les modules du projet depuis la racine
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_image_index() -> dict[str, str]:
    cache_file = settings.data_dir / "wuddai_entities_cache.json"
    if not cache_file.exists():
        print(f"Cache wudd.ai introuvable : {cache_file}")
        return {}
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    return {
        entity["value_normalized"]: entity["image_url"]
        for entity in data.get("entities", [])
        if entity.get("image_url") and entity.get("value_normalized")
    }


def _extract_entity_name(content: str) -> str | None:
    match = re.search(r"^entity_name:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    # fallback : H1
    match = re.search(r"^# (.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def _find_frontmatter_close(lines: list[str]) -> int | None:
    """Retourne l'index de la ligne --- fermant le frontmatter, ou None."""
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return None


def _has_image(content: str) -> bool:
    lines = content.split("\n")
    close = _find_frontmatter_close(lines)
    if close is None:
        return False
    for line in lines[close + 1: close + 5]:
        stripped = line.strip()
        if stripped.startswith("!["):
            return True
        if stripped:
            break
    return False


def _insert_image(content: str, entity_name: str, image_url: str) -> str:
    """Insère la ligne image juste après le bloc frontmatter fermant."""
    lines = content.split("\n")
    close = _find_frontmatter_close(lines)
    if close is None:
        return content
    img_line = f"![{entity_name}]({image_url})"
    new_lines = lines[:close + 1] + ["", img_line] + lines[close + 1:]
    return "\n".join(new_lines)


def main() -> None:
    entities_dir = settings.entities_dir
    if not entities_dir.exists():
        print(f"Répertoire entities introuvable : {entities_dir}")
        return

    image_index = _load_image_index()
    if not image_index:
        print("Index image vide — abandon.")
        return

    notes = list(entities_dir.glob("*.md"))
    print(f"{len(notes)} notes d'entités trouvées dans {entities_dir}")

    updated = 0
    skipped_no_image = 0
    skipped_already = 0

    for note_path in notes:
        content = note_path.read_text(encoding="utf-8", errors="replace")

        if _has_image(content):
            skipped_already += 1
            continue

        entity_name = _extract_entity_name(content)
        if not entity_name:
            continue

        normalized = _normalize(entity_name)
        image_url = image_index.get(normalized)
        if not image_url:
            skipped_no_image += 1
            continue

        new_content = _insert_image(content, entity_name, image_url)
        if new_content != content:
            note_path.write_text(new_content, encoding="utf-8")
            print(f"  ✓ {note_path.name} — image ajoutée")
            updated += 1

    print(
        f"\nTerminé : {updated} note(s) patchée(s), "
        f"{skipped_already} déjà à jour, "
        f"{skipped_no_image} sans image wudd.ai."
    )


if __name__ == "__main__":
    main()
