#!/usr/bin/env python3
"""
Script de renommage des insights/synapses via IA.

Pour chaque note dans obsirag/insights, obsirag/synapses et obsirag/synthesis :
  1. Demande au LLM un titre court et représentatif (3-7 mots)
     → L'extrait fourni au LLM commence toujours au corps de la note (après le frontmatter),
       pour éviter que les tags YAML consomment le contexte utile.
  2. Renomme le fichier .md
  3. Met à jour le champ `title` dans le frontmatter
  4. Remplace [[ancien_titre]] → [[nouveau_titre]] dans TOUT le vault
  5. Met à jour synapse_index.json (liste de paires "fp_a|||fp_b" en chemins relatifs au vault)
  6. Re-indexe dans ChromaDB les fichiers wikilinks modifiés + la note renommée

Options :
  --dry-run        Simule sans écrire (utile pour prévisualiser)
  --dir <cible>    insights | synapses | synthesis | all (défaut : all)
  --no-llm         Nettoyage simple : retire le suffixe _YYYYMMDD, underscores → espaces
  --sleep <s>      Pause entre appels LLM en secondes (défaut : 5)

Usage (dans Docker) :
  docker exec obsirag python3 /app/scripts/rename_insights.py
  docker exec obsirag python3 /app/scripts/rename_insights.py --dry-run
  docker exec obsirag python3 /app/scripts/rename_insights.py --dir insights --sleep 2
  docker exec obsirag python3 /app/scripts/rename_insights.py --no-llm --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")
from src.config import settings

# ── Helpers frontmatter ────────────────────────────────────────────────────────

def _fm_end(content: str) -> int:
    if not content.startswith("---"):
        return -1
    matches = list(re.finditer(r"^---[ \t]*$", content, re.MULTILINE))
    if len(matches) < 2:
        return -1
    end = matches[1].end()
    if end < len(content) and content[end] == "\n":
        end += 1
    return end


def _set_fm_title(content: str, new_title: str) -> str:
    """Ajoute ou remplace le champ `title` dans le frontmatter."""
    end = _fm_end(content)
    if end == -1:
        return f"---\ntitle: {new_title}\n---\n" + content
    fm = content[3:end]
    if re.search(r"^title\s*:", fm, re.MULTILINE):
        fm = re.sub(r"^(title\s*:).*$", f"title: {new_title}", fm, flags=re.MULTILINE)
    else:
        fm = f"title: {new_title}\n" + fm
    return "---\n" + fm + content[end:]


def _get_h1(content: str) -> str:
    """Extrait le premier titre H1 du corps de la note."""
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else ""


# ── LLM ───────────────────────────────────────────────────────────────────────

def _suggest_title(llm, content: str, current_stem: str) -> str | None:
    """
    Demande au LLM un titre court. Retourne None si le titre actuel convient
    ou si la suggestion est invalide.
    """
    # Toujours sauter le frontmatter pour ne pas gaspiller le contexte LLM
    end = _fm_end(content)
    body = content[end:] if end != -1 else content
    excerpt = body[:1200]
    prompt = (
        f"Voici le début d'une note générée automatiquement, "
        f"dont le nom de fichier actuel est : \"{current_stem}\"\n\n"
        f"<contenu>\n{excerpt}\n</contenu>\n\n"
        f"Propose un titre court (3 à 7 mots) en français représentatif du contenu, "
        f"sans guillemets, sans ponctuation finale, sans préfixe. "
        f"Si le titre actuel est déjà clair et court, réponds exactement : CONSERVER\n"
        f"Sinon, réponds uniquement avec le nouveau titre."
    )
    try:
        result = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=40,
            operation="rename_script",
        )
        candidate = result.strip().strip('"').strip("'")
        if not candidate or candidate.upper() == "CONSERVER":
            return None
        if len(candidate) > 100:
            return None
        if candidate.lower().strip() == current_stem.lower().replace("_", " ").strip():
            return None
        return candidate
    except Exception as exc:
        print(f"  ⚠ LLM error: {exc}")
        return None


# ── Renommage + propagation ────────────────────────────────────────────────────

def _safe_stem(title: str) -> str:
    """Transforme un titre en nom de fichier safe (sans caractères interdits)."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe


def rename_file(
    old_path: Path,
    new_title: str,
    vault: Path,
    dry_run: bool,
    indexer=None,
) -> Path | None:
    """
    Renomme old_path, propage les wikilinks dans le vault, re-indexe.
    Retourne le nouveau chemin ou None si annulé.
    """
    old_stem = old_path.stem
    new_stem = _safe_stem(new_title)

    if new_stem == old_stem:
        return None

    new_path = old_path.parent / f"{new_stem}.md"

    if new_path.exists():
        print(f"  ⚠ Conflit : '{new_path.name}' existe déjà — ignoré")
        return None

    if dry_run:
        print(f"  [dry-run] '{old_stem}' → '{new_stem}'")
        return new_path

    # 1. Renommer le fichier
    old_path.rename(new_path)

    # 2. Mettre à jour le frontmatter title
    try:
        content = new_path.read_text(encoding="utf-8")
        content = _set_fm_title(content, new_stem)
        new_path.write_text(content, encoding="utf-8")
    except Exception as exc:
        print(f"  ⚠ Frontmatter update: {exc}")

    # 3. Propager [[old_stem]] → [[new_stem]] dans tout le vault
    pattern = re.compile(
        r"\[\[" + re.escape(old_stem) + r"([\|#\]])",
        re.IGNORECASE,
    )
    replacement = "[[" + new_stem + r"\1"
    updated = 0
    for md_file in vault.rglob("*.md"):
        if md_file == new_path:
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            if old_stem.lower() in text.lower():
                new_text = pattern.sub(replacement, text)
                if new_text != text:
                    md_file.write_text(new_text, encoding="utf-8")
                    updated += 1
                    if indexer:
                        indexer.index_note(md_file)
        except Exception as exc:
            print(f"  ⚠ wikilink update in '{md_file.name}': {exc}")

    # 4. Mettre à jour synapse_index.json
    synapse_file = settings.synapse_index_file
    if synapse_file.exists():
        try:
            old_rel = str(old_path.relative_to(vault))
            new_rel = str(new_path.relative_to(vault))
            pairs: list[str] = json.loads(synapse_file.read_text(encoding="utf-8"))
            new_pairs = [
                p.replace(old_rel, new_rel) if old_rel in p else p
                for p in pairs
            ]
            if new_pairs != pairs:
                synapse_file.write_text(
                    json.dumps(new_pairs, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                changed = sum(1 for a, b in zip(pairs, new_pairs) if a != b)
                updated_synapse_msg = f", synapse_index: {changed} entrée(s)"
            else:
                updated_synapse_msg = ""
        except Exception as exc:
            print(f"  ⚠ synapse_index update: {exc}")
            updated_synapse_msg = ""
    else:
        updated_synapse_msg = ""

    # 5. Re-indexer la note renommée (invalider l'ancien rel_path)
    if indexer:
        try:
            indexer.remove_note(old_path)
        except Exception:
            pass
        indexer.index_note(new_path)

    print(f"  ✅ '{old_stem}' → '{new_stem}' (wikilinks: {updated} fichier(s){updated_synapse_msg})")
    return new_path


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Renomme les insights/synapses via IA.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simule sans écrire",
    )
    parser.add_argument(
        "--dir", choices=["insights", "synapses", "synthesis", "all"], default="all",
        help="Dossier cible (default: all)",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Renomme uniquement en nettoyant le nom existant (sans LLM)",
    )
    parser.add_argument(
        "--sleep", type=float, default=5.0,
        help="Pause entre deux appels LLM en secondes (default: 5)",
    )
    args = parser.parse_args()

    vault = settings.vault

    # Dossiers cibles
    dirs_map = {
        "insights":  settings.insights_dir,
        "synapses":  settings.synapses_dir,
        "synthesis": settings.synthesis_dir,
    }
    if args.dir == "all":
        target_dirs = list(dirs_map.values())
    else:
        target_dirs = [dirs_map[args.dir]]

    # Initialiser le LLM et l'indexer (seulement si pas dry-run)
    llm = None
    indexer = None
    if not args.dry_run and not args.no_llm:
        try:
            from src.ai.ollama_client import OllamaClient
            llm = OllamaClient()
            if not llm.is_available():
                print("⚠ Ollama non disponible — mode --no-llm activé")
                llm = None
        except Exception as exc:
            print(f"⚠ LLM init failed: {exc} — mode --no-llm activé")
            llm = None

    if not args.dry_run:
        try:
            from src.database.chroma_store import ChromaStore
            from src.indexer.pipeline import IndexingPipeline
            chroma = ChromaStore()
            indexer = IndexingPipeline(chroma)
        except Exception as exc:
            print(f"⚠ ChromaDB/Indexer init failed: {exc} — re-indexation désactivée")

    # Collecter tous les fichiers .md des dossiers cibles
    files: list[Path] = []
    for d in target_dirs:
        if d.exists():
            files.extend(sorted(d.rglob("*.md")))

    if not files:
        print("Aucun fichier trouvé dans les dossiers cibles.")
        return

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Traitement de {len(files)} note(s)…\n")

    renamed = 0
    skipped = 0

    for md_path in files:
        current_stem = md_path.stem
        print(f"→ {md_path.relative_to(vault)}")

        content = md_path.read_text(encoding="utf-8")

        if args.no_llm or llm is None:
            # Nettoyage simple : enlever le suffixe _YYYYMMDD si présent
            clean = re.sub(r"_\d{8}$", "", current_stem)
            clean = clean.replace("_", " ").strip()
            # Tronquer à 60 chars
            if len(clean) > 60:
                clean = clean[:60].rsplit(" ", 1)[0]
            new_title = clean if clean != current_stem.replace("_", " ") else None
        else:
            new_title = _suggest_title(llm, content, current_stem)
            time.sleep(args.sleep)

        if not new_title:
            print(f"  — conservé")
            skipped += 1
            continue

        result = rename_file(md_path, new_title, vault, args.dry_run, indexer)
        if result:
            renamed += 1
        else:
            skipped += 1

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Terminé : {renamed} renommé(s), {skipped} conservé(s)")


if __name__ == "__main__":
    main()
