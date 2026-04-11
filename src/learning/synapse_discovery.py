from __future__ import annotations

import json
import random
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.learning.autolearn import AutoLearner


class AutoLearnSynapseDiscovery:
    def __init__(self, owner: "AutoLearner") -> None:
        self._owner = owner

    def load_synapse_index(self) -> set[str]:
        file_path = self._owner._get_settings().synapse_index_file
        if file_path.exists():
            try:
                return set(json.loads(file_path.read_text(encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def save_synapse_index(self, index: set[str]) -> None:
        file_path = self._owner._get_settings().synapse_index_file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(sorted(index), ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def synapse_pair_key(file_path_a: str, file_path_b: str) -> str:
        return "|||".join(sorted([file_path_a, file_path_b]))

    def discover_synapses(self, all_notes: list[dict]) -> None:
        quota = self._owner._get_settings().autolearn_synapse_per_run
        if quota <= 0:
            return

        synapse_index = self._owner._load_synapse_index()
        candidates = list(all_notes)
        random.shuffle(candidates)

        for note_a in candidates:
            if quota <= 0:
                break
            file_path_a = note_a["file_path"]
            existing_links = {wikilink.lower() for wikilink in note_a.get("wikilinks", [])}
            similar = self._owner._chroma.find_similar_notes(
                source_fp=file_path_a,
                existing_links=existing_links,
                top_k=5,
                threshold=self._owner._get_settings().autolearn_synapse_threshold,
            )

            for note_b_info in similar:
                if quota <= 0:
                    break
                file_path_b = note_b_info["file_path"]
                pair_key = self._owner._synapse_pair_key(file_path_a, file_path_b)
                if pair_key in synapse_index:
                    continue
                try:
                    self._owner._create_synapse_artifact(note_a, note_b_info)
                    synapse_index.add(pair_key)
                    self._owner._save_synapse_index(synapse_index)
                    quota -= 1
                    time.sleep(self._owner._SLEEP_BETWEEN_QUESTIONS)
                except Exception as exc:
                    logger.warning(f"Synapse {file_path_a} ↔ {file_path_b} : {exc}")

    def create_synapse_artifact(self, note_a: dict, note_b_info: dict) -> None:
        title_a = note_a.get("title", note_a["file_path"])
        title_b = note_b_info["title"]
        score = note_b_info["score"]
        excerpt_b = note_b_info["excerpt"]

        chunks_a = self._owner._chroma.search(title_a, top_k=1)
        excerpt_a = chunks_a[0]["text"][:300] if chunks_a else ""
        prompt = (
            f"Voici deux notes d'un coffre Obsidian qui semblent liées thématiquement "
            f"(similarité sémantique : {score:.0%}) mais sans lien explicite entre elles.\n\n"
            f"**Note A — {title_a} :**\n{excerpt_a}\n\n"
            f"**Note B — {title_b} :**\n{excerpt_b}\n\n"
            f"En 3 à 5 phrases, explique quelle connexion implicite unit ces deux notes, "
            f"comme une synapse qui relie deux neurones. Propose aussi une question que "
            f"l'utilisateur pourrait se poser pour approfondir ce lien. Réponds en français."
        )

        explanation = self._owner._rag._llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=2048,
            operation="autolearn_synapse",
        )

        safe_a = re.sub(r"[^\w\s-]", "", title_a).strip().replace(" ", "_")[:40]
        safe_b = re.sub(r"[^\w\s-]", "", title_b).strip().replace(" ", "_")[:40]
        date_str = datetime.now(UTC).strftime("%Y%m%d")
        out_dir = self._owner._get_settings().synapses_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{safe_a}__{safe_b}_{date_str}.md"

        lines = [
            f"# Synapse : {title_a} ↔ {title_b}",
            "",
            f"**Similarité sémantique :** {score:.0%}  ",
            f"**Découverte le :** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC",
            "",
            "---",
            "",
            "## Connexion identifiée",
            "",
            explanation,
            "",
            "---",
            "",
            f"## [[{title_a}]]",
            "",
            f"> {excerpt_a[:600]}…",
            "",
            f"## [[{title_b}]]",
            "",
            f"> {excerpt_b[:600]}…",
        ]
        out_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Synapse créée : {title_a} ↔ {title_b} ({score:.0%})")