from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.learning.autolearn import AutoLearner


class AutoLearnArtifactWriter:
    def __init__(self, owner: "AutoLearner") -> None:
        self._owner = owner

    @staticmethod
    def wikilink(file_path: str) -> str:
        return f"[[{file_path.removesuffix('.md')}]]"

    @staticmethod
    def compute_global_provenance(qa_pairs: list[dict]) -> str:
        provenances = {qa.get("provenance", "Coffre") for qa in qa_pairs}
        if "Coffre et Web" in provenances or ("Coffre" in provenances and "Web" in provenances):
            return "Coffre et Web"
        if "Web" in provenances:
            return "Web"
        return "Coffre"

    def render_qa_sections(
        self,
        qa_pairs: list[dict],
        *,
        start_index: int = 1,
        provenance: str,
    ) -> list[str]:
        lines: list[str] = []
        for index, qa in enumerate(qa_pairs, start_index):
            provenance_label = qa.get("provenance", provenance)
            source_links = ", ".join(self.wikilink(source) for source in qa["sources"] if source)
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

    def find_existing_insight(self, note_title: str, ner_tags: list[str]) -> Path | None:
        insights_root = self._owner._get_settings().insights_dir
        if not insights_root.exists():
            return None

        safe_name = re.sub(r"[^\w\s-]", "", note_title).strip().replace(" ", "_")[:60].lower()
        new_ner_set = {tag for tag in ner_tags if "/" in tag}

        best_path: Path | None = None
        best_score = 0
        for path in insights_root.rglob("*.md"):
            score = 0
            if path.stem.lower().startswith(safe_name):
                score += 10
            if new_ner_set:
                try:
                    existing_tags = self._owner._read_frontmatter_tags(path.read_text(encoding="utf-8"))
                    existing_ner = {tag for tag in existing_tags if "/" in tag}
                    overlap = len(new_ner_set & existing_ner)
                    if overlap >= 2:
                        score += overlap * 2
                except Exception:
                    pass
            if score > best_score:
                best_score = score
                best_path = path
        return best_path if best_score >= 4 else None

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
        lines.extend(self.render_qa_sections(qa_pairs, provenance=global_provenance))
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
        content = path.read_text(encoding="utf-8")
        existing_count = len(re.findall(r"^## Question \d+", content, re.MULTILINE))
        content = self._owner._merge_frontmatter_tags(content, ner_tags)
        content = self.maybe_add_frontmatter_location(content, entity_images)
        content = re.sub(
            r"\*\*(Générée|Mise à jour) le :\*\*.*",
            f"**Mise à jour le :** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            content,
        )
        content = self.upsert_entity_gallery(content, entity_images)

        new_lines = [""]
        new_lines.extend(self.render_qa_sections(qa_pairs, start_index=existing_count + 1, provenance=provenance))
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

        existing = self._owner._find_existing_insight(note_title, ner_tags)
        if existing:
            self._owner._append_to_insight(existing, qa_pairs, ner_tags, global_provenance, entity_images)
            return

        date_str = datetime.now().strftime("%Y-%m")
        artifact_dir = self._owner._get_settings().insights_dir / date_str
        artifact_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r"[^\w\s-]", "", note_title).strip().replace(" ", "_")[:60]
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