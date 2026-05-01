"""
Tests unitaires — Parser de notes (src/vault/parser.py)
Utilise un mock spaCy pour éviter le téléchargement du modèle NER.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.vault.parser import NoteEntities, NoteParser, NoteSection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def parser(mock_nlp):
    """NoteParser avec spaCy mocké."""
    with patch("src.vault.parser.get_nlp", return_value=mock_nlp):
        yield NoteParser()


@pytest.fixture
def note_with_frontmatter(tmp_path):
    p = tmp_path / "note.md"
    p.write_text(
        "---\ntitle: Ma Note\ntags: [python, ia]\ndate: 2026-01-15\n---\n\n"
        "Contenu principal.\n\n"
        "## Section 1\n\nContenu de la section 1.\n\n"
        "## Section 2\n\nContenu de la section 2.\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def note_without_frontmatter(tmp_path):
    p = tmp_path / "simple.md"
    p.write_text("Juste du contenu sans frontmatter.\n\nDeuxième paragraphe.\n", encoding="utf-8")
    return p


@pytest.fixture
def note_with_wikilinks(tmp_path):
    p = tmp_path / "wikilinks.md"
    p.write_text(
        "---\ntitle: Note avec liens\n---\n\n"
        "Voir [[Note Python]] et [[IA Générative|Gen AI]] pour plus d'infos.\n"
        "Aussi [[Note vide]] est intéressante.\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def configure_vault(tmp_settings, monkeypatch):
    """Applique tmp_settings comme settings global."""
    monkeypatch.setattr("src.vault.parser.settings", tmp_settings)
    return tmp_settings


# ---------------------------------------------------------------------------
# Tests NoteEntities
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNoteEntities:
    def test_all_entities_combines_lists(self):
        e = NoteEntities(
            persons=["Alice", "Bob"],
            orgs=["ACME"],
            locations=["Paris"],
            misc=["Python"],
        )
        all_e = e.all_entities()
        assert "Alice" in all_e
        assert "ACME" in all_e
        assert len(all_e) == 5

    def test_as_metadata_returns_strings(self):
        e = NoteEntities(persons=["Alice"], orgs=["ACME"], locations=[], misc=[])
        meta = e.as_metadata()
        assert meta["ner_persons"] == "Alice"
        assert meta["ner_orgs"] == "ACME"
        assert meta["ner_locations"] == ""
        assert meta["ner_misc"] == ""

    def test_as_metadata_truncates_at_30(self):
        e = NoteEntities(persons=[f"Personne{i}" for i in range(50)])
        meta = e.as_metadata()
        count = len(meta["ner_persons"].split(","))
        assert count == 30

    def test_empty_entities(self):
        e = NoteEntities()
        assert e.all_entities() == []
        meta = e.as_metadata()
        assert all(v == "" for v in meta.values())


# ---------------------------------------------------------------------------
# Tests NoteParser — parsing de base
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNoteParserBasic:
    def test_parse_returns_none_for_missing_file(self, parser, tmp_path):
        result = parser.parse(tmp_path / "inexistant.md")
        assert result is None

    def test_parse_extracts_title_from_frontmatter(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert result is not None
        assert result.metadata.title == "Ma Note"

    def test_parse_uses_stem_as_title_fallback(self, parser, note_without_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_without_frontmatter)
        assert result is not None
        assert result.metadata.title == "simple"

    def test_parse_uses_first_alias_as_title_fallback(self, tmp_path, mock_nlp):
        p = tmp_path / "alias.md"
        p.write_text(
            "---\naliases: [Alias Principal, Alias 2]\n---\n\nContenu.\n",
            encoding="utf-8",
        )
        s = MagicMock()
        s.vault = tmp_path
        with patch("src.vault.parser.settings", s), patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            np = NoteParser()
            result = np.parse(p)
        assert result is not None
        assert result.metadata.title == "Alias Principal"

    def test_parse_extracts_frontmatter_tags(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert "python" in result.metadata.tags
        assert "ia" in result.metadata.tags

    def test_parse_body_tags_extracted(self, tmp_path, mock_nlp):
        p = tmp_path / "body_tags.md"
        p.write_text("Texte avec #datascience et #ia ici.\n", encoding="utf-8")
        s = MagicMock()
        s.vault = tmp_path
        with patch("src.vault.parser.settings", s), patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            np = NoteParser()
            result = np.parse(p)
        assert "datascience" in result.metadata.tags
        assert "ia" in result.metadata.tags

    def test_parse_file_hash_is_string(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert isinstance(result.metadata.file_hash, str)
        assert len(result.metadata.file_hash) == 32  # MD5 hex

    def test_parse_date_modified_is_datetime(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert isinstance(result.metadata.date_modified, datetime)

    def test_parse_rel_path(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert result.metadata.file_path == "note.md"

    def test_parse_sanitizes_invalid_yaml_control_characters(self, parser, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        note = tmp_path / "invalid_control.md"
        note.write_text(
            "---\ntitle: Mon\x9ctitre\ntags: [ia]\n---\n\nContenu avec caractère de contrôle.\n",
            encoding="utf-8",
        )

        result = parser.parse(note)

        assert result is not None
        assert result.metadata.title == "Montitre"
        assert "ia" in result.metadata.tags


# ---------------------------------------------------------------------------
# Tests NoteParser — wikilinks
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNoteParserWikilinks:
    def test_extracts_wikilinks(self, parser, note_with_wikilinks, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_wikilinks)
        assert "Note Python" in result.metadata.wikilinks
        assert "Note vide" in result.metadata.wikilinks

    def test_wikilinks_deduplicated(self, tmp_path, mock_nlp):
        p = tmp_path / "dup.md"
        p.write_text("---\ntitle: T\n---\n[[A]] et [[A]] encore [[A]].\n", encoding="utf-8")
        s = MagicMock()
        s.vault = tmp_path
        with patch("src.vault.parser.settings", s), patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            np = NoteParser()
            result = np.parse(p)
        assert result.metadata.wikilinks.count("A") == 1

    def test_wikilink_with_alias_ignored(self, parser, note_with_wikilinks, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_wikilinks)
        # [[IA Générative|Gen AI]] → titre = "IA Générative"
        assert "IA Générative" in result.metadata.wikilinks
        assert "Gen AI" not in result.metadata.wikilinks


# ---------------------------------------------------------------------------
# Tests NoteParser — sections
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNoteParserSections:
    def test_split_sections_counts(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        # Intro + Section 1 + Section 2
        assert len(result.sections) == 3

    def test_intro_section_has_level_0(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert result.sections[0].level == 0
        assert result.sections[0].title == ""

    def test_header_sections_have_correct_level(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert result.sections[1].level == 2
        assert result.sections[1].title == "Section 1"
        assert result.sections[2].title == "Section 2"

    def test_no_sections_when_no_headers(self, mock_nlp, tmp_path):
        p = tmp_path / "flat.md"
        p.write_text("---\ntitle: Flat\n---\nJuste un paragraphe.\n", encoding="utf-8")
        s = MagicMock()
        s.vault = tmp_path
        with patch("src.vault.parser.settings", s), patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            np = NoteParser()
            result = np.parse(p)
        assert len(result.sections) == 1
        assert result.sections[0].level == 0

    def test_empty_note_sections_empty(self, mock_nlp, tmp_path):
        p = tmp_path / "empty.md"
        p.write_text("---\ntitle: Vide\n---\n\n", encoding="utf-8")
        s = MagicMock()
        s.vault = tmp_path
        with patch("src.vault.parser.settings", s), patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            np = NoteParser()
            result = np.parse(p)
        assert result.sections == []

    def test_split_sections_keeps_empty_header_body(self, parser):
        sections = parser._split_sections("# Titre\n")
        assert len(sections) == 1
        assert sections[0].title == "Titre"
        assert sections[0].content == ""


# ---------------------------------------------------------------------------
# Tests NoteParser — raw_content
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNoteParserRawContent:
    def test_raw_content_excludes_frontmatter(self, parser, note_with_frontmatter, configure_vault, tmp_path):
        configure_vault.vault_path = str(tmp_path)
        result = parser.parse(note_with_frontmatter)
        assert "---" not in result.raw_content
        assert "title:" not in result.raw_content
        assert "Contenu principal" in result.raw_content


@pytest.mark.unit
class TestNoteParserHelpers:
    def test_parse_fm_date_supports_multiple_string_formats(self, parser):
        assert parser._parse_fm_date("2026-01-15") == datetime(2026, 1, 15)
        assert parser._parse_fm_date("2026-01-15T13:45:00") == datetime(2026, 1, 15, 13, 45, 0)
        assert parser._parse_fm_date("15/01/2026") == datetime(2026, 1, 15)
        assert parser._parse_fm_date("2026/01/15") == datetime(2026, 1, 15)

    def test_parse_fm_date_returns_datetime_as_is(self, parser):
        value = datetime(2026, 1, 15, 10, 30, 0)
        assert parser._parse_fm_date(value) is value

    def test_parse_fm_date_invalid_returns_none(self, parser):
        assert parser._parse_fm_date("15-01-2026") is None
        assert parser._parse_fm_date(123) is None

    def test_extract_entities_routes_labels_and_deduplicates(self, parser):
        entity_specs = [
            ("Alice", "PER"),
            ("Alice", "PER"),
            ("ACME", "ORG"),
            ("Paris", "GPE"),
            ("MLX", "TECH"),
            ("X", "PER"),
        ]
        ents = [MagicMock(text=text, label_=label) for text, label in entity_specs]
        mock_nlp = MagicMock()
        mock_doc = MagicMock(ents=ents)
        mock_nlp.return_value = mock_doc
        with patch("src.vault.parser.get_nlp", return_value=mock_nlp):
            extracted = parser._extract_entities("Contenu")

        assert extracted.persons == ["Alice"]
        assert extracted.orgs == ["ACME"]
        assert extracted.locations == ["Paris"]
        assert extracted.misc == ["MLX"]
        mock_nlp.assert_called_once_with("Contenu")

    def test_extract_entities_returns_empty_on_nlp_failure(self, parser):
        with patch("src.vault.parser.get_nlp", side_effect=RuntimeError("boom")):
            extracted = parser._extract_entities("Contenu")
        assert extracted == NoteEntities()


@pytest.mark.unit
class TestGetNlp:
    def test_get_nlp_loads_and_disables_unused_pipes(self, monkeypatch):
        from src.vault import parser as parser_module

        mock_model = MagicMock()
        mock_model.pipe_names = ["tok2vec", "tagger", "ner"]
        monkeypatch.setattr(parser_module, "_nlp", None)

        with patch("src.vault.parser.spacy.load", return_value=mock_model):
            result = parser_module.get_nlp()

        assert result is mock_model
        mock_model.disable_pipes.assert_called_once_with(["tok2vec", "tagger"])

    def test_get_nlp_raises_when_model_missing(self, monkeypatch):
        from src.vault import parser as parser_module

        monkeypatch.setattr(parser_module, "_nlp", None)
        with patch("src.vault.parser.spacy.load", side_effect=OSError("missing")):
            with pytest.raises(OSError):
                parser_module.get_nlp()
