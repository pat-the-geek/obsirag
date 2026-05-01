"""
Parsing des notes Obsidian (Markdown + frontmatter YAML).
Extraction : sections, wikilinks, tags, entités NER.
"""
import re
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import frontmatter
import spacy
from loguru import logger

from src.config import settings


# ---------------------------------------------------------------------------
# Modèle NER (chargé une seule fois)
# ---------------------------------------------------------------------------
_nlp: Optional[spacy.language.Language] = None

_DISALLOWED_CONTROL_TRANSLATION = {
    **{code: None for code in range(0x00, 0x20) if code not in (0x09, 0x0A, 0x0D)},
    **{code: None for code in range(0x7F, 0xA0)},
}


def get_nlp() -> spacy.language.Language:
    global _nlp
    if _nlp is None:
        logger.info(f"Chargement du modèle NER : {settings.ner_model}")
        try:
            _nlp = spacy.load(settings.ner_model)
            # Désactiver les composants inutiles pour gagner en vitesse
            _nlp.disable_pipes([p for p in _nlp.pipe_names if p not in ("ner",)])
        except OSError:
            logger.error(
                f"Modèle spaCy '{settings.ner_model}' introuvable. "
                "Exécutez : python -m spacy download xx_ent_wiki_sm"
            )
            raise
    return _nlp


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------

@dataclass
class NoteSection:
    title: str
    level: int   # 0 = intro avant le premier header
    content: str


@dataclass
class NoteEntities:
    persons: list[str] = field(default_factory=list)
    orgs: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    misc: list[str] = field(default_factory=list)

    def all_entities(self) -> list[str]:
        return self.persons + self.orgs + self.locations + self.misc

    def as_metadata(self) -> dict[str, str]:
        """Sérialise pour ChromaDB (valeurs str)."""
        return {
            "ner_persons": ",".join(self.persons[:30]),
            "ner_orgs": ",".join(self.orgs[:30]),
            "ner_locations": ",".join(self.locations[:30]),
            "ner_misc": ",".join(self.misc[:30]),
        }


@dataclass
class NoteMetadata:
    file_path: str        # relatif au coffre
    title: str
    date_modified: datetime
    date_created: datetime
    tags: list[str]
    wikilinks: list[str]
    entities: NoteEntities
    frontmatter: dict
    file_hash: str


@dataclass
class ParsedNote:
    metadata: NoteMetadata
    raw_content: str      # contenu sans frontmatter
    sections: list[NoteSection]


# ---------------------------------------------------------------------------
# Parser principal
# ---------------------------------------------------------------------------

class NoteParser:
    _WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+?)(?:[|#][^\]]*?)?\]\]")
    _TAG_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9_\-/]+)", re.MULTILINE)
    _HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def parse(self, file_path: Path) -> Optional[ParsedNote]:
        try:
            # Lire les octets bruts d'abord pour un hash cohérent avec pipeline._file_hash()
            raw_bytes = file_path.read_bytes()
            file_hash = hashlib.md5(raw_bytes).hexdigest()
            raw = raw_bytes.decode("utf-8", errors="replace")
            sanitized_raw = self._strip_disallowed_control_chars(raw)
            stat = file_path.stat()

            post = frontmatter.loads(sanitized_raw)
            fm: dict = dict(post.metadata)
            body: str = post.content

            title = fm.get("title") or fm.get("aliases", [None])[0] or file_path.stem
            rel_path = str(file_path.relative_to(settings.vault))

            date_created = self._parse_fm_date(fm.get("date") or fm.get("created")) \
                or datetime.fromtimestamp(stat.st_ctime)
            date_modified = datetime.fromtimestamp(stat.st_mtime)

            tags = list({
                *[t for t in fm.get("tags", []) if isinstance(t, str)],
                *self._TAG_RE.findall(body),
            })

            wikilinks = list({m.strip() for m in self._WIKILINK_RE.findall(body)})

            entities = self._extract_entities(body)
            sections = self._split_sections(body)

            metadata = NoteMetadata(
                file_path=rel_path,
                title=str(title),
                date_modified=date_modified,
                date_created=date_created,
                tags=tags,
                wikilinks=wikilinks,
                entities=entities,
                frontmatter=fm,
                file_hash=file_hash,
            )

            return ParsedNote(metadata=metadata, raw_content=body, sections=sections)

        except Exception as exc:
            logger.warning(f"Impossible de parser {file_path.name} : {exc}")
            return None

    # ---- helpers ----

    def _extract_entities(self, text: str) -> NoteEntities:
        ents = NoteEntities()
        try:
            nlp = get_nlp()
            # Tronquer pour ne pas saturer la mémoire sur les très longues notes
            doc = nlp(text[:50_000])
            for ent in doc.ents:
                label = ent.label_
                value = ent.text.strip()
                if not value or len(value) < 2:
                    continue
                if label == "PER":
                    ents.persons.append(value)
                elif label == "ORG":
                    ents.orgs.append(value)
                elif label in ("LOC", "GPE"):
                    ents.locations.append(value)
                else:
                    ents.misc.append(value)
            # Déduplique en conservant l'ordre
            ents.persons = list(dict.fromkeys(ents.persons))
            ents.orgs = list(dict.fromkeys(ents.orgs))
            ents.locations = list(dict.fromkeys(ents.locations))
            ents.misc = list(dict.fromkeys(ents.misc))
        except Exception as exc:
            logger.debug(f"NER échoué : {exc}")
        return ents

    def _split_sections(self, content: str) -> list[NoteSection]:
        sections: list[NoteSection] = []
        headers = list(self._HEADER_RE.finditer(content))

        if not headers:
            if content.strip():
                sections.append(NoteSection(title="", level=0, content=content.strip()))
            return sections

        # Intro avant le premier header
        intro = content[: headers[0].start()].strip()
        if intro:
            sections.append(NoteSection(title="", level=0, content=intro))

        for i, match in enumerate(headers):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
            body = content[start:end].strip()
            sections.append(NoteSection(title=title, level=level, content=body))

        return sections

    def _parse_fm_date(self, value) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _strip_disallowed_control_chars(value: str) -> str:
        return value.translate(_DISALLOWED_CONTROL_TRANSLATION)
