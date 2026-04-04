"""
Découpage intelligent des notes en chunks pour l'indexation.
Stratégie hiérarchique : section → paragraphe → mots
avec préservation du contexte (chevauchement).
"""
from dataclasses import dataclass

from src.config import settings
from src.vault.parser import NoteMetadata, NoteSection


@dataclass
class Chunk:
    text: str
    chunk_id: str        # "{file_hash}_{chunk_index}"
    chunk_index: int
    note_title: str
    file_path: str
    section_title: str
    section_level: int
    date_modified: str   # ISO 8601 (affichage)
    date_created: str    # ISO 8601 (affichage)
    date_modified_ts: float  # Unix timestamp (filtrage ChromaDB)
    date_created_ts: float   # Unix timestamp (filtrage ChromaDB)
    tags: str            # séparé par ","
    wikilinks: str       # séparé par ","
    ner_persons: str
    ner_orgs: str
    ner_locations: str
    ner_misc: str
    file_hash: str

    def as_metadata(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "note_title": self.note_title,
            "file_path": self.file_path,
            "section_title": self.section_title,
            "section_level": self.section_level,
            "date_modified": self.date_modified,
            "date_created": self.date_created,
            "date_modified_ts": self.date_modified_ts,
            "date_created_ts": self.date_created_ts,
            "tags": self.tags,
            "wikilinks": self.wikilinks,
            "ner_persons": self.ner_persons,
            "ner_orgs": self.ner_orgs,
            "ner_locations": self.ner_locations,
            "ner_misc": self.ner_misc,
            "file_hash": self.file_hash,
        }


class TextChunker:
    def __init__(
        self,
        chunk_size: int = settings.chunk_size_words,
        overlap: int = settings.chunk_overlap_words,
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_note(self, metadata: NoteMetadata, sections: list[NoteSection]) -> list[Chunk]:
        chunks: list[Chunk] = []
        ner_meta = metadata.entities.as_metadata()
        base_meta = {
            "note_title": metadata.title,
            "file_path": metadata.file_path,
            "date_modified": metadata.date_modified.isoformat(),
            "date_created": metadata.date_created.isoformat(),
            "date_modified_ts": metadata.date_modified.timestamp(),
            "date_created_ts": metadata.date_created.timestamp(),
            "tags": ",".join(metadata.tags[:50]),
            "wikilinks": ",".join(metadata.wikilinks[:30]),
            "file_hash": metadata.file_hash,
            **ner_meta,
        }

        global_index = 0
        for section in sections:
            if not section.content.strip():
                continue
            for text in self._split_section(section):
                chunk = Chunk(
                    text=text,
                    chunk_id=f"{metadata.file_hash}_{global_index}",
                    chunk_index=global_index,
                    section_title=section.title,
                    section_level=section.level,
                    **base_meta,
                )
                chunks.append(chunk)
                global_index += 1

        return chunks

    # ---- split helpers ----

    def _split_section(self, section: NoteSection) -> list[str]:
        words = section.content.split()
        if len(words) <= self.chunk_size:
            return [section.content.strip()] if section.content.strip() else []

        # Pour les sections très longues, on tente de couper aux sauts de paragraphe
        paragraphs = [p.strip() for p in section.content.split("\n\n") if p.strip()]
        if len(paragraphs) > 1:
            return self._merge_paragraphs(paragraphs)

        # Fallback : découpage par fenêtre glissante de mots
        return self._sliding_window(words)

    def _merge_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """Fusionne les paragraphes jusqu'à chunk_size mots, puis crée un nouveau chunk."""
        chunks: list[str] = []
        current_words: list[str] = []
        overlap_words: list[str] = []

        for para in paragraphs:
            para_words = para.split()
            if current_words and len(current_words) + len(para_words) > self.chunk_size:
                chunks.append(" ".join(current_words))
                overlap_words = current_words[-self.overlap:] if self.overlap else []
                current_words = overlap_words + para_words
            else:
                current_words.extend(para_words)

        if current_words:
            chunks.append(" ".join(current_words))

        return chunks

    def _sliding_window(self, words: list[str]) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(words):
            end = min(start + self.chunk_size, len(words))
            chunks.append(" ".join(words[start:end]))
            start += self.chunk_size - self.overlap
        return chunks
