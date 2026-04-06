#!/usr/bin/env python3
"""
Script de reprise — migration des tags NER et ajout géolocalisation dans les insights.

À la 1ère exécution :
  - Remplace les anciens tags NER (personne/*, org/*, lieu/*) par les tags validés
    contre la liste officielle WUDD.ai
  - Supprime les tags NER non présents dans la liste officielle
  - Injecte `location: [lat, lng]` dans le frontmatter pour les entités GPE/LOC
  - Ajoute la galerie d'images si absente

Usage (dans Docker) :
  docker exec obsirag python3 /app/scripts/migrate_insight_tags.py
  docker exec obsirag python3 /app/scripts/migrate_insight_tags.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/app")
from src.config import settings

# ── Constantes ────────────────────────────────────────────────────────────────
_NER_PREFIXES = ("personne/", "org/", "lieu/", "produit/", "event/", "groupe/")
_WUDDAI_TYPE_TO_PREFIX: dict[str, str] = {
    "PERSON":  "personne",
    "ORG":     "org",
    "GPE":     "lieu",
    "LOC":     "lieu",
    "PRODUCT": "produit",
    "EVENT":   "event",
    "NORP":    "groupe",
    "FAC":     "lieu",
}
_IMAGE_TYPES = ["PERSON", "ORG", "GPE", "PRODUCT"]


# ── Helpers ────────────────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _slug(value: str) -> str:
    n = _normalize(value)
    n = re.sub(r"[^\w\s-]", "", n).strip()
    return re.sub(r"[\s_]+", "-", n)


# ── Chargement entités WUDD.ai ─────────────────────────────────────────────────
def load_wuddai_entities() -> list[dict]:
    cache_file = settings.data_dir / "wuddai_entities_cache.json"
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached.get("fetched_at", "2000-01-01"))
            if datetime.utcnow() - fetched_at < timedelta(hours=24):
                print(f"  Cache WUDD.ai utilisé ({len(cached['entities'])} entités)")
                return cached["entities"]
        except Exception:
            pass
    print(f"  Chargement depuis {settings.wuddai_entities_url} …")
    url = f"{settings.wuddai_entities_url}/api/entities/export?limit=5000&images=true"
    req = urllib.request.Request(url, headers={"User-Agent": "ObsiRAG-migration/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    entities = [
        {
            "type":             e["type"],
            "value":            e["value"],
            "value_normalized": _normalize(e["value"]),
            "mentions":         e.get("mentions", 0),
            "image_url":        e.get("image", {}).get("url") if e.get("image") else None,
        }
        for e in data.get("entities", [])
    ]
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"fetched_at": datetime.utcnow().isoformat(), "entities": entities},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  {len(entities)} entités chargées depuis WUDD.ai")
    return entities


# ── Geocodage Wikipedia ────────────────────────────────────────────────────────
_geo_cache: dict[str, list[float] | None] = {}
_geo_cache_file: Path | None = None


def _load_geo_cache() -> None:
    global _geo_cache, _geo_cache_file
    _geo_cache_file = settings.data_dir / "geocode_cache.json"
    if _geo_cache_file.exists():
        try:
            _geo_cache = json.loads(_geo_cache_file.read_text(encoding="utf-8"))
        except Exception:
            _geo_cache = {}


def _save_geo_cache() -> None:
    if _geo_cache_file:
        try:
            _geo_cache_file.write_text(
                json.dumps(_geo_cache, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass


def fetch_coordinates(entity_name: str) -> tuple[float, float] | None:
    key = _normalize(entity_name)
    if key in _geo_cache:
        v = _geo_cache[key]
        return (v[0], v[1]) if v else None
    coords = None
    for lang in ("fr", "en"):
        try:
            params = urllib.parse.urlencode({
                "action": "query", "prop": "coordinates",
                "titles": entity_name, "format": "json", "redirects": "1",
            })
            req = urllib.request.Request(
                f"https://{lang}.wikipedia.org/w/api.php?{params}",
                headers={"User-Agent": "ObsiRAG-migration/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            for page in d.get("query", {}).get("pages", {}).values():
                c = page.get("coordinates", [])
                if c:
                    coords = (c[0]["lat"], c[0]["lon"])
                    break
            if coords:
                break
        except Exception:
            pass
    _geo_cache[key] = list(coords) if coords else None
    return coords


# ── Frontmatter helpers ────────────────────────────────────────────────────────
def _fm_end(content: str) -> int:
    """
    Retourne la position du premier caractère APRÈS la ligne de fermeture ---
    du frontmatter YAML. Retourne -1 si pas de frontmatter valide.
    Utilise ^---$ (start-of-line) pour éviter les faux positifs dans le contenu.
    """
    if not content.startswith("---"):
        return -1
    matches = list(re.finditer(r"^---[ \t]*$", content, re.MULTILINE))
    if len(matches) < 2:
        return -1
    # matches[0] = ouverture, matches[1] = fermeture
    end = matches[1].end()
    if end < len(content) and content[end] == "\n":
        end += 1
    return end

def read_frontmatter_tags(content: str) -> list[str]:
    if not content.startswith("---"):
        return []
    end = _fm_end(content)
    if end == -1:
        return []
    yaml_block = content[3:end]  # entre opening --- et fin du FM
    tags: list[str] = []
    in_tags = False
    for line in yaml_block.splitlines():
        if re.match(r"^tags\s*:", line):
            in_tags = True
            continue
        if in_tags:
            m = re.match(r"\s+-\s+(.+)", line)
            if m:
                tags.append(m.group(1).strip())
            elif line.strip() and not line.startswith(" "):
                in_tags = False
    return tags


def rewrite_frontmatter(content: str, new_tags: list[str],
                        coords: tuple[float, float] | None) -> str:
    """Réécrit le frontmatter en imposant les tags validés et location."""
    fm_tags = "\n".join(f"  - {t}" for t in new_tags)
    location_line = (f"\nlocation: [{coords[0]:.6f}, {coords[1]:.6f}]"
                     if coords else "")
    new_fm = f"---\ntags:\n{fm_tags}{location_line}\n---\n"
    end = _fm_end(content)
    if end == -1:
        return new_fm + content
    # content[end:] = tout ce qui suit la ligne --- de fermeture
    body = content[end:]
    # Supprimer une éventuelle section ## Entités clés au début du body
    # (vestige d'une migration précédente corrompue)
    body = re.sub(r"^\s*## Entités clés.*?(?=\n#|\n---\n|\Z)", "", body,
                  flags=re.DOTALL)
    return new_fm + body.lstrip("\n")


# ── Galerie d'images ───────────────────────────────────────────────────────────
def build_gallery(entity_images: list[dict]) -> str:
    if not entity_images:
        return ""
    by_type: dict[str, dict] = {}
    for e in entity_images:
        if e["type"] not in by_type:
            by_type[e["type"]] = e
    selected = [by_type[t] for t in _IMAGE_TYPES if t in by_type]
    if not selected:
        return ""
    header = " | ".join(f"![{e['value']}]({e['image_url']})" for e in selected)
    labels = " | ".join(f"**{e['value']}**"                           for e in selected)
    sep    = " | ".join(":---:"                                        for _ in selected)
    return f"| {header} |\n| {sep} |\n| {labels} |\n"


def inject_gallery(content: str, gallery_md: str) -> str:
    """Insère ou remplace la section ## Entités clés APRÈS le frontmatter."""
    if not gallery_md:
        return content
    gallery_block = f"## Entités clés\n\n{gallery_md}\n"
    if "## Entités clés" in content:
        return re.sub(
            r"## Entités clés\n.*?(?=\n#|\n---\n|\Z)",
            f"## Entités clés\n\n{gallery_md}\n",
            content,
            flags=re.DOTALL,
        )
    # Insérer APRÈS la fermeture --- du frontmatter
    end = _fm_end(content)
    if end != -1:
        return content[:end] + gallery_block + "\n" + content[end:]
    return gallery_block + "\n" + content


# ── Migration d'un fichier ─────────────────────────────────────────────────────
def migrate_file(
    path: Path,
    wuddai_index: dict[str, dict],
    dry_run: bool,
) -> dict:
    content = path.read_text(encoding="utf-8")
    existing_tags = read_frontmatter_tags(content)

    # 1. Séparer tags structurels et tags NER
    structural_tags = [t for t in existing_tags if not any(t.startswith(p) for p in _NER_PREFIXES)]
    old_ner_tags    = [t for t in existing_tags if any(t.startswith(p) for p in _NER_PREFIXES)]

    # 2. Extraire les noms bruts des anciens tags NER
    #    ex: "personne/sam-altman" → "sam altman"
    raw_names: list[str] = []
    for tag in old_ner_tags:
        for prefix in _NER_PREFIXES:
            if tag.startswith(prefix):
                raw = tag[len(prefix):].replace("-", " ")
                raw_names.append(raw)
                break

    # 3. Valider chaque nom contre WUDD.ai
    new_ner_tags: list[str] = []
    entity_images: list[dict] = []
    seen_tags: set[str] = set()
    seen_vals: set[str] = set()
    removed: list[str] = []
    kept:    list[str] = []

    for raw in raw_names:
        normalized = _normalize(raw)
        match = wuddai_index.get(normalized)
        if not match:
            # Recherche partielle
            for key, ent in wuddai_index.items():
                if (normalized in key or key in normalized) and abs(len(normalized) - len(key)) <= 5:
                    match = ent
                    break
        if not match:
            removed.append(raw)
            continue
        official_value = match["value"]
        official_type  = match["type"]
        prefix = _WUDDAI_TYPE_TO_PREFIX.get(official_type)
        if not prefix:
            removed.append(raw)
            continue
        new_tag = f"{prefix}/{_slug(official_value)}"
        if new_tag not in seen_tags:
            seen_tags.add(new_tag)
            new_ner_tags.append(new_tag)
            kept.append(f"{raw} → {new_tag}")
        if official_type in _IMAGE_TYPES and match.get("image_url") and official_value not in seen_vals:
            seen_vals.add(official_value)
            entity_images.append({
                "type":      official_type,
                "value":     official_value,
                "image_url": match["image_url"],
                "mentions":  match.get("mentions", 0),
            })

    entity_images.sort(key=lambda e: (
        _IMAGE_TYPES.index(e["type"]) if e["type"] in _IMAGE_TYPES else 99,
        -e["mentions"],
    ))

    # 4. Géolocalisation
    gpe_entities = [e for e in entity_images if e["type"] in ("GPE", "LOC")]
    coords: tuple[float, float] | None = None
    if gpe_entities:
        coords = fetch_coordinates(gpe_entities[0]["value"])

    # 5. Reconstruction frontmatter
    all_tags = structural_tags + new_ner_tags
    new_content = rewrite_frontmatter(content, all_tags, coords)

    # 6. Galerie d'images
    gallery_md = build_gallery(entity_images)
    if gallery_md:
        new_content = inject_gallery(new_content, gallery_md)

    changed = new_content != content
    if changed and not dry_run:
        path.write_text(new_content, encoding="utf-8")

    return {
        "file": path.name,
        "changed": changed,
        "removed": removed,
        "kept": kept,
        "coords": coords,
        "gallery": bool(gallery_md),
    }


# ── Point d'entrée ─────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Migration NER tags + géolocalisation insights")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simule sans écrire les fichiers")
    args = parser.parse_args()

    print("=" * 60)
    print("ObsiRAG — Migration NER tags & géolocalisation insights")
    print("=" * 60)
    if args.dry_run:
        print("  MODE DRY-RUN : aucun fichier ne sera modifié\n")

    # Charger les entités WUDD.ai
    print("\n[1/3] Chargement des entités WUDD.ai …")
    try:
        entities = load_wuddai_entities()
    except Exception as exc:
        print(f"  ERREUR : impossible de charger les entités WUDD.ai : {exc}")
        sys.exit(1)
    wuddai_index: dict[str, dict] = {e["value_normalized"]: e for e in entities}

    # Charger le cache de géocodage
    print("\n[2/3] Chargement du cache de géocodage …")
    _load_geo_cache()

    # Parcourir les insights
    insights_root = settings.insights_dir
    if not insights_root.exists():
        print(f"\n  Aucun répertoire insights trouvé : {insights_root}")
        sys.exit(0)

    md_files = list(insights_root.rglob("*.md"))
    print(f"\n[3/3] Traitement de {len(md_files)} fichier(s) dans {insights_root} …\n")

    stats = {"changed": 0, "unchanged": 0, "tags_removed": 0, "tags_kept": 0,
             "geolocated": 0, "galleries": 0}

    for path in sorted(md_files):
        result = migrate_file(path, wuddai_index, dry_run=args.dry_run)
        status = "✏️ " if result["changed"] else "  "
        geo    = f" 📍({result['coords'][0]:.2f},{result['coords'][1]:.2f})" if result["coords"] else ""
        gal    = " 🖼️" if result["gallery"] else ""
        print(f"{status}{result['file']}{geo}{gal}")
        if result["removed"]:
            for r in result["removed"]:
                print(f"     ❌ supprimé : {r}")
        if result["kept"]:
            for k in result["kept"]:
                print(f"     ✅ {k}")
        if result["changed"]:
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1
        stats["tags_removed"] += len(result["removed"])
        stats["tags_kept"]    += len(result["kept"])
        if result["coords"]:
            stats["geolocated"] += 1
        if result["gallery"]:
            stats["galleries"] += 1

    # Sauvegarder le cache géo mis à jour
    _save_geo_cache()

    print("\n" + "=" * 60)
    print(f"  Fichiers modifiés  : {stats['changed']}")
    print(f"  Fichiers inchangés : {stats['unchanged']}")
    print(f"  Tags supprimés     : {stats['tags_removed']}")
    print(f"  Tags validés       : {stats['tags_kept']}")
    print(f"  Notes géolocalisées: {stats['geolocated']}")
    print(f"  Galeries ajoutées  : {stats['galleries']}")
    if args.dry_run:
        print("\n  ⚠️  DRY-RUN — aucune modification écrite.")
    print("=" * 60)


if __name__ == "__main__":
    main()
