from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from src.storage.safe_read import read_text_file
from src.storage.slugify import build_ascii_stem

if TYPE_CHECKING:
    from src.learning.autolearn import AutoLearner


class AutoLearnArtifactWriter:
    def __init__(self, owner: "AutoLearner") -> None:
        self._owner = owner

    @staticmethod
    def normalize_provenance_label(provenance: str | None) -> str:
        value = (provenance or "Coffre").strip()
        if value in {"Web + Coffre", "Coffre + Web", "Coffre et Web"}:
            return "Coffre et Web"
        return value or "Coffre"

    @staticmethod
    def wikilink(file_path: str) -> str:
        return f"[[{file_path.removesuffix('.md')}]]"

    @staticmethod
    def _is_obsirag_generated_path(file_path: str) -> bool:
        normalized = str(file_path or "").replace("\\", "/")
        return "/obsirag/" in normalized or normalized.startswith("obsirag/")

    @classmethod
    def filter_source_paths(cls, sources: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for source in sources:
            value = str(source or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)

        user_sources = [source for source in cleaned if not cls._is_obsirag_generated_path(source)]
        return user_sources or cleaned

    @staticmethod
    def compute_global_provenance(qa_pairs: list[dict]) -> str:
        normalized = {
            AutoLearnArtifactWriter.normalize_provenance_label(qa.get("provenance", "Coffre"))
            for qa in qa_pairs
        }
        if "Coffre et Web" in normalized or ("Coffre" in normalized and "Web" in normalized):
            return "Coffre et Web"
        if "Web" in normalized:
            return "Web"
        return "Coffre"

    @staticmethod
    def _extract_global_provenance(content: str) -> str:
        match = re.search(r"^\*\*Provenance :\*\*\s+(.+)$", content, re.MULTILINE)
        if not match:
            return "Coffre"
        return AutoLearnArtifactWriter.normalize_provenance_label(match.group(1).strip())

    def render_qa_sections(
        self,
        qa_pairs: list[dict],
        *,
        start_index: int = 1,
        provenance: str,
        source_note_path: str = "",
    ) -> list[str]:
        lines: list[str] = []
        for index, qa in enumerate(qa_pairs, start_index):
            provenance_label = self.normalize_provenance_label(qa.get("provenance", provenance))
            filtered_sources = self.filter_source_paths(qa.get("sources", []))
            if (
                source_note_path
                and not self._is_obsirag_generated_path(source_note_path)
                and (
                    not filtered_sources
                    or all(self._is_obsirag_generated_path(source) for source in filtered_sources)
                )
            ):
                filtered_sources = [source_note_path]
            source_links = ", ".join(self.wikilink(source) for source in filtered_sources if source)
            lines.extend([
                f"## Question {index}",
                "",
                f"> {qa['question']}",
                "",
                qa["answer"],
                "",
                f"*Provenance : {provenance_label}*  ",
                f"*Notes consultées : {source_links}*  " if source_links else "",
            ])
            if qa.get("web_refs"):
                lines.append("*Références web :*")
                lines.extend(f"- [{ref['title']}]({ref['url']})" for ref in qa["web_refs"])
            lines.append("")
        return lines

    def render_web_synthesis_section(self, note_title: str, qa_pairs: list[dict]) -> list[str]:
        web_synthesis = self._owner._synthesize_web_sources(note_title, qa_pairs)
        if not web_synthesis:
            return []
        return [
            "---",
            "",
            "## Synthèse des sources web",
            "",
            web_synthesis,
            "",
        ]

    def maybe_add_frontmatter_location(self, content: str, entity_images: list[dict] | None) -> str:
        if not entity_images or "location:" in content[:content.find("---", 3) + 3]:
            return content
        gpe_entities = [entity for entity in entity_images if entity["type"] in ("GPE", "LOC")]
        if not gpe_entities:
            return content
        coords = self._owner._fetch_gpe_coordinates(gpe_entities[0]["value"])
        if not coords:
            return content
        return self._owner._add_location_to_frontmatter(content, coords[0], coords[1])

    def upsert_entity_gallery(self, content: str, entity_images: list[dict] | None) -> str:
        if not entity_images:
            return content
        gallery_md = self._owner._build_entity_image_gallery(entity_images)
        if not gallery_md:
            return content
        gallery_block = f"## Entités clés\n\n{gallery_md}\n"
        if "## Entités clés" in content:
            return re.sub(
                r"## Entités clés\n.*?(?=\n---\n|\n## )",
                gallery_block,
                content,
                flags=re.DOTALL,
            )
        return re.sub(
            r"(## Question 1\b)",
            gallery_block + "\n---\n\n" + r"\1",
            content,
            count=1,
        )

    @staticmethod
    def _extract_source_note_ref(content: str) -> str | None:
        match = re.search(r"^\*\*Note source :\*\* \[\[(.+?)\]\]", content, re.MULTILINE)
        if not match:
            return None
        return match.group(1).strip()

    @classmethod
    def extract_source_note_ref(cls, content: str) -> str | None:
        return cls._extract_source_note_ref(content)

    def find_existing_insight(
        self,
        note_title: str,
        ner_tags: list[str],
        *,
        source_tags: list[str] | None = None,
        source_note_path: str = "",
    ) -> Path | None:
        insights_root = self._owner._get_settings().insights_dir
        if not insights_root.exists():
            return None

        safe_name = build_ascii_stem(note_title, fallback="insight", max_length=60, separator="_").lower()
        new_ner_set = {tag for tag in ner_tags if "/" in tag}
        new_source_tag_set = {tag for tag in (source_tags or []) if tag and "/" not in tag and tag != "insight"}
        source_note_ref = source_note_path.removesuffix(".md") if source_note_path else ""

        candidate_paths: list[Path] = []
        list_insight_notes = getattr(self._owner._chroma, "list_insight_notes", None)
        if callable(list_insight_notes):
            try:
                notes = list_insight_notes()
                if isinstance(notes, list):
                    vault_root = self._owner._get_settings().vault
                    candidate_paths = [
                        vault_root / note["file_path"]
                        for note in notes
                        if isinstance(note, dict) and note.get("file_path")
                    ]
            except Exception:
                candidate_paths = []
        if not candidate_paths:
            # Prefer shallow monthly layout first (obsirag/insights/YYYY-MM/*.md), then fallback.
            fallback_started_at = time.perf_counter()
            candidate_paths = list(insights_root.glob("*/*.md"))
            self._record_metric(
                "autolearn_fs_fallback_insight_glob_total",
                elapsed=time.perf_counter() - fallback_started_at,
                observe_metric="autolearn_fs_fallback_insight_glob_seconds",
            )
            if not candidate_paths:
                fallback_started_at = time.perf_counter()
                candidate_paths = list(insights_root.rglob("*.md"))
                self._record_metric(
                    "autolearn_fs_fallback_insight_rglob_total",
                    elapsed=time.perf_counter() - fallback_started_at,
                    observe_metric="autolearn_fs_fallback_insight_rglob_seconds",
                )

        best_path: Path | None = None
        best_score = 0
        for path in candidate_paths:
            # Ignorer les fichiers archivés (suffixe _archive_YYYYMMDD_HHMMSS)
            if re.search(r"_archive_\d{8}_\d{6}", path.stem):
                continue
            if safe_name and path.stem.lower().startswith(safe_name):
                # Fast path: title-prefix match is strong enough and avoids costly file reads.
                score = 10
            else:
                score = 0
                try:
                    content = read_text_file(path, default="")
                except Exception:
                    content = ""

                if source_note_ref:
                    existing_source_ref = self._extract_source_note_ref(content)
                    if existing_source_ref == source_note_ref:
                        score = 9

                if score == 0 and new_ner_set and new_source_tag_set:
                    try:
                        existing_tags = self._owner._read_frontmatter_tags(content)
                        existing_ner = {tag for tag in existing_tags if "/" in tag}
                        existing_source_tags = {tag for tag in existing_tags if "/" not in tag and tag != "insight"}
                        overlap = len(new_ner_set & existing_ner)
                        source_overlap = len(new_source_tag_set & existing_source_tags)
                        if overlap >= 2 and source_overlap >= 1:
                            score += overlap * 2 + source_overlap
                    except Exception:
                        pass
            if score > best_score:
                best_score = score
                best_path = path
        return best_path if best_score >= 5 else None

    def _record_metric(
        self,
        increment_metric: str,
        *,
        elapsed: float | None = None,
        observe_metric: str | None = None,
    ) -> None:
        metrics = getattr(self._owner, "_metrics", None)
        if metrics is None:
            return
        try:
            metrics.increment(increment_metric)
            if observe_metric and elapsed is not None:
                metrics.observe(observe_metric, max(0.0, float(elapsed)))
        except Exception:
            pass

    def build_new_insight_document(
        self,
        note_title: str,
        note_meta: dict,
        qa_pairs: list[dict],
        source_tags: list[str],
        ner_tags: list[str],
        entity_images: list[dict],
        global_provenance: str,
    ) -> str:
        all_tags = ["insight"] + source_tags + ner_tags
        fm_tags = "\n".join(f"  - {tag}" for tag in all_tags)

        gpe_entities = [entity for entity in entity_images if entity["type"] in ("GPE", "LOC")]
        coords = self._owner._fetch_gpe_coordinates(gpe_entities[0]["value"]) if gpe_entities else None
        fm_location = f"\nlocation: [{coords[0]:.6f}, {coords[1]:.6f}]" if coords else ""
        frontmatter = f"---\ntags:\n{fm_tags}{fm_location}\n---\n"

        lines = [
            frontmatter,
            f"# Insights : {note_title}",
            "",
            f"**Note source :** {self.wikilink(note_meta['file_path'])}  ",
            f"**Générée le :** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC  ",
            f"**Tags source :** {source_tags}  ",
            f"**Provenance :** {global_provenance}",
            "",
        ]

        gallery_md = self._owner._build_entity_image_gallery(entity_images)
        if gallery_md:
            lines.extend([
                "## Entités clés",
                "",
                gallery_md,
            ])

        lines.extend([
            "---",
            "",
        ])
        lines.extend(
            self.render_qa_sections(
                qa_pairs,
                provenance=global_provenance,
                source_note_path=note_meta.get("file_path", ""),
            )
        )
        lines.extend(self.render_web_synthesis_section(note_title, qa_pairs))
        return "\n".join(lines)

    def append_to_insight(
        self,
        path: Path,
        qa_pairs: list[dict],
        ner_tags: list[str],
        provenance: str,
        entity_images: list[dict] | None = None,
    ) -> None:
        content = read_text_file(path, default="")
        existing_count = len(re.findall(r"^## Question \d+", content, re.MULTILINE))
        content = self._owner._merge_frontmatter_tags(content, ner_tags)
        content = self.maybe_add_frontmatter_location(content, entity_images)
        existing_global_provenance = self._extract_global_provenance(content)
        updated_global_provenance = self.compute_global_provenance([
            {"provenance": existing_global_provenance},
            {"provenance": provenance},
        ])
        content = re.sub(
            r"\*\*(Générée|Mise à jour) le :\*\*.*",
            f"**Mise à jour le :** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            content,
        )
        content = re.sub(
            r"^\*\*Provenance :\*\*\s+.+$",
            f"**Provenance :** {updated_global_provenance}",
            content,
            flags=re.MULTILINE,
        )
        content = self.upsert_entity_gallery(content, entity_images)
        source_note_path = self._extract_source_note_ref(content) or ""

        new_lines = [""]
        new_lines.extend(
            self.render_qa_sections(
                qa_pairs,
                start_index=existing_count + 1,
                provenance=provenance,
                source_note_path=source_note_path,
            )
        )
        new_lines.extend(self.render_web_synthesis_section(path.stem, qa_pairs))
        path.write_text(content.rstrip() + "\n" + "\n".join(new_lines), encoding="utf-8")

        current_size = path.stat().st_size
        if current_size > self._owner._get_settings().max_insight_size_bytes:
            archive_path = path.with_stem(path.stem + f"_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            path.rename(archive_path)
            logger.warning(
                f"Artefact archivé (trop grand {current_size // 1024} KB > "
                f"{self._owner._get_settings().max_insight_size_bytes // 1024} KB) : {path.name} → {archive_path.name}"
            )
        else:
            try:
                self._owner._metrics.increment("autolearn_insights_appended_total")
            except Exception:
                pass
            logger.info(
                f"Artefact mis à jour : {path.name} (+{len(qa_pairs)} Q&A → total {existing_count + len(qa_pairs)})"
            )

    def save_knowledge_artifact(self, note_title: str, note_meta: dict, qa_pairs: list[dict]) -> None:
        global_provenance = self.compute_global_provenance(qa_pairs)
        qa_text = " ".join(qa["question"] + " " + qa["answer"] for qa in qa_pairs)
        ner_tags, entity_images = self._owner._extract_validated_entities(qa_text)
        source_tags = [tag for tag in note_meta.get("tags", []) if tag]

        existing = self._owner._find_existing_insight(
            note_title,
            ner_tags,
            source_tags=source_tags,
            source_note_path=note_meta.get("file_path", ""),
        )
        if existing:
            self._owner._append_to_insight(existing, qa_pairs, ner_tags, global_provenance, entity_images)
            return

        date_str = datetime.now().strftime("%Y-%m")
        artifact_dir = self._owner._get_settings().insights_dir / date_str
        artifact_dir.mkdir(parents=True, exist_ok=True)

        safe_name = build_ascii_stem(note_title, fallback="insight", max_length=60, separator="_")
        artifact_path = artifact_dir / f"{safe_name}_{datetime.now().strftime('%Y%m%d')}.md"
        artifact_path.write_text(
            self.build_new_insight_document(
                note_title,
                note_meta,
                qa_pairs,
                source_tags,
                ner_tags,
                entity_images,
                global_provenance,
            ),
            encoding="utf-8",
        )
        try:
            self._owner._metrics.increment("autolearn_insights_created_total")
        except Exception:
            pass
        logger.info(f"Artefact créé : {artifact_path.name}")