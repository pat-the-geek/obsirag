from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from loguru import logger


class AutoLearnNoteRenamer:
    def __init__(self, owner: Any) -> None:
        self._owner = owner

    def suggest_note_title(self, content_preview: str, current_title: str) -> str | None:
        prompt = (
            f"Voici un extrait d'une note personnelle intitulée actuellement : \"{current_title}\"\n\n"
            f"<extrait>\n{content_preview[:1500]}\n</extrait>\n\n"
            f"Propose un titre court (3 à 7 mots maximum) OBLIGATOIREMENT EN FRANÇAIS, représentatif du contenu réel, "
            f"sans guillemets, sans ponctuation finale, sans préfixe comme 'Titre :'. "
            f"IMPORTANT : le titre doit être en français, même si le contenu est dans une autre langue. "
            f"Si le titre actuel est déjà représentatif, réponds exactement : CONSERVER\n"
            f"Sinon, réponds uniquement avec le nouveau titre en français."
        )
        try:
            result = self._owner._rag._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=50,
                operation="autolearn_rename",
            )
            candidate = result.strip().strip('"').strip("'")
            if not candidate or candidate.upper() == "CONSERVER":
                return None
            if len(candidate) > 80:
                return None
            if re.search(r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]", candidate):
                return None
            if candidate.lower().strip() == current_title.lower().strip():
                return None
            return candidate
        except Exception as exc:
            logger.debug(f"Suggestion titre échouée pour '{current_title}': {exc}")
            return None

    def rename_note_in_vault(self, old_abs: Path, new_title: str, note_rel: str) -> Path | None:
        settings = self._owner._get_settings()
        vault = settings.vault

        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", new_title).strip()
        safe = re.sub(r"\s+", " ", safe)
        new_abs = old_abs.parent / f"{safe}.md"

        if new_abs.exists() and new_abs != old_abs:
            logger.warning(f"Rename abort: '{new_abs.name}' existe déjà")
            return None

        old_stem = old_abs.stem
        new_stem = new_abs.stem

        try:
            old_abs.rename(new_abs)
        except Exception as exc:
            logger.error(f"Impossible de renommer '{old_abs.name}': {exc}")
            return None

        logger.info(f"Note renommée : '{old_stem}' → '{new_stem}'")

        self._update_frontmatter_title(new_abs, new_stem)
        updated_files = self._update_vault_wikilinks(vault, old_stem, new_stem, skip_file=new_abs)
        if updated_files:
            logger.info(f"Wikilinks mis à jour dans {updated_files} fichier(s)")

        try:
            self._owner._indexer.remove_note(old_abs)
        except Exception:
            pass
        self._owner._indexer.index_note(new_abs)
        self._migrate_processed_map(vault, note_rel, new_abs)
        return new_abs

    def _update_frontmatter_title(self, note_path: Path, new_stem: str) -> None:
        try:
            content = note_path.read_text(encoding="utf-8")
            fm_end = self._owner._fm_end(content)
            if fm_end != -1:
                frontmatter = content[3:fm_end]
                if re.search(r"^title\s*:", frontmatter, re.MULTILINE):
                    frontmatter = re.sub(r"^(title\s*:).*$", f"title: {new_stem}", frontmatter, flags=re.MULTILINE)
                else:
                    frontmatter = f"title: {new_stem}\n" + frontmatter
                content = "---\n" + frontmatter + content[fm_end:]
            else:
                content = f"---\ntitle: {new_stem}\n---\n" + content
            note_path.write_text(content, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Maj frontmatter title échouée: {exc}")

    def _update_vault_wikilinks(self, vault: Path, old_stem: str, new_stem: str, *, skip_file: Path) -> int:
        pattern = re.compile(r"\[\[" + re.escape(old_stem) + r"([\|#\]])", re.IGNORECASE)
        replacement = r"[[" + new_stem + r"\1"
        updated_files = 0
        for md_file in vault.rglob("*.md"):
            if md_file == skip_file:
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
                if old_stem.lower() not in text.lower():
                    continue
                new_text = pattern.sub(replacement, text)
                if new_text == text:
                    continue
                md_file.write_text(new_text, encoding="utf-8")
                updated_files += 1
                self._owner._indexer.index_note(md_file)
            except Exception as exc:
                logger.warning(f"Update wikilinks dans '{md_file.name}': {exc}")
        return updated_files

    def _migrate_processed_map(self, vault: Path, note_rel: str, new_abs: Path) -> None:
        try:
            new_rel = str(new_abs.relative_to(vault))
            processed = self._owner._load_processed()
            if note_rel in processed:
                processed[new_rel] = processed.pop(note_rel)
                self._owner._save_processed(processed)
                logger.debug(f"processed_map migré : '{note_rel}' → '{new_rel}'")
        except Exception as exc:
            logger.warning(f"processed_map migration rename : {exc}")