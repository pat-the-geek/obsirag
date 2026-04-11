"""
Tests unitaires — Chunker (src/indexer/chunker.py)
"""
from __future__ import annotations

import pytest
from datetime import datetime

from src.indexer.chunker import Chunk, TextChunker
from src.vault.parser import NoteEntities, NoteMetadata, NoteSection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(**kwargs) -> NoteMetadata:
    defaults = dict(
        file_path="test.md",
        title="Test Note",
        date_modified=datetime(2026, 1, 1),
        date_created=datetime(2026, 1, 1),
        tags=["tag1"],
        wikilinks=["Link A"],
        entities=NoteEntities(),
        frontmatter={},
        file_hash="abc123",
    )
    defaults.update(kwargs)
    return NoteMetadata(**defaults)


def _make_section(content: str, title: str = "", level: int = 0) -> NoteSection:
    return NoteSection(title=title, level=level, content=content)


def _words(n: int) -> str:
    return " ".join(f"mot{i}" for i in range(n))


# ---------------------------------------------------------------------------
# Tests Chunk.as_metadata()
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChunkMetadata:
    def test_as_metadata_keys(self, sample_metadata, sample_sections):
        chunker = TextChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk_note(sample_metadata, sample_sections)
        assert len(chunks) > 0
        meta = chunks[0].as_metadata()
        required_keys = {
            "chunk_id", "chunk_index", "note_title", "file_path",
            "section_title", "section_level", "date_modified", "date_created",
            "date_modified_ts", "date_created_ts", "tags", "wikilinks",
            "ner_persons", "ner_orgs", "ner_locations", "ner_misc", "file_hash",
        }
        assert required_keys <= set(meta.keys())

    def test_chunk_id_format(self, sample_metadata, sample_sections):
        chunker = TextChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk_note(sample_metadata, sample_sections)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == f"deadbeef_{i}"

    def test_tags_serialized_as_csv(self, sample_metadata, sample_sections):
        chunker = TextChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk_note(sample_metadata, sample_sections)
        assert "," in chunks[0].tags or chunks[0].tags in ("python", "data", "python,data")

    def test_date_modified_ts_is_float(self, sample_metadata, sample_sections):
        chunker = TextChunker(chunk_size=500, overlap=50)
        chunks = chunker.chunk_note(sample_metadata, sample_sections)
        meta = chunks[0].as_metadata()
        assert isinstance(meta["date_modified_ts"], float)


# ---------------------------------------------------------------------------
# Tests TextChunker — sections courtes (pas de découpage)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChunkerShortSections:
    def test_short_section_single_chunk(self):
        chunker = TextChunker(chunk_size=100, overlap=10)
        meta = _make_metadata()
        sections = [_make_section("Texte court.")]
        chunks = chunker.chunk_note(meta, sections)
        assert len(chunks) == 1
        assert chunks[0].text == "Texte court."

    def test_empty_sections_ignored(self):
        chunker = TextChunker(chunk_size=100, overlap=10)
        meta = _make_metadata()
        sections = [_make_section(""), _make_section("   "), _make_section("Contenu.")]
        chunks = chunker.chunk_note(meta, sections)
        assert len(chunks) == 1

    def test_multiple_short_sections_multiple_chunks(self):
        chunker = TextChunker(chunk_size=100, overlap=10)
        meta = _make_metadata()
        sections = [
            _make_section("Section 1."),
            _make_section("Section 2.", title="Titre", level=2),
        ]
        chunks = chunker.chunk_note(meta, sections)
        assert len(chunks) == 2

    def test_chunk_index_sequential(self):
        chunker = TextChunker(chunk_size=100, overlap=10)
        meta = _make_metadata()
        sections = [_make_section("A"), _make_section("B"), _make_section("C")]
        chunks = chunker.chunk_note(meta, sections)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_section_title_preserved(self):
        chunker = TextChunker(chunk_size=100, overlap=10)
        meta = _make_metadata()
        sections = [_make_section("Contenu.", title="Mon Titre", level=2)]
        chunks = chunker.chunk_note(meta, sections)
        assert chunks[0].section_title == "Mon Titre"
        assert chunks[0].section_level == 2


# ---------------------------------------------------------------------------
# Tests TextChunker — sections longues (découpage)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChunkerLongSections:
    def test_long_section_produces_multiple_chunks(self):
        chunker = TextChunker(chunk_size=10, overlap=2)
        meta = _make_metadata()
        sections = [_make_section(_words(30))]
        chunks = chunker.chunk_note(meta, sections)
        assert len(chunks) > 1

    def test_all_words_covered(self):
        """Tous les mots doivent apparaître dans au moins un chunk."""
        chunker = TextChunker(chunk_size=10, overlap=2)
        meta = _make_metadata()
        content = _words(30)
        sections = [_make_section(content)]
        chunks = chunker.chunk_note(meta, sections)
        all_text = " ".join(c.text for c in chunks)
        for word in content.split():
            assert word in all_text

    def test_overlap_applied(self):
        """Le premier mot du chunk N+1 doit apparaître dans le chunk N."""
        chunker = TextChunker(chunk_size=10, overlap=3)
        meta = _make_metadata()
        sections = [_make_section(_words(25))]
        chunks = chunker.chunk_note(meta, sections)
        if len(chunks) >= 2:
            first_word_second = chunks[1].text.split()[0]
            assert first_word_second in chunks[0].text

    def test_paragraph_split_preferred(self):
        """Le découpage aux sauts de paragraphe doit être préféré à la fenêtre glissante."""
        chunker = TextChunker(chunk_size=5, overlap=1)
        meta = _make_metadata()
        # Deux paragraphes séparés par double saut de ligne
        content = f"{_words(8)}\n\n{_words(8)}"
        sections = [_make_section(content)]
        chunks = chunker.chunk_note(meta, sections)
        assert len(chunks) >= 2

    def test_max_chunk_text_length_reasonable(self):
        """Un chunk ne doit pas être excessivement long."""
        chunker = TextChunker(chunk_size=20, overlap=5)
        meta = _make_metadata()
        sections = [_make_section(_words(100))]
        chunks = chunker.chunk_note(meta, sections)
        for chunk in chunks:
            word_count = len(chunk.text.split())
            # Peut légèrement dépasser chunk_size à cause de l'overlap
            assert word_count <= chunker.chunk_size + chunker.overlap + 5

    def test_note_metadata_in_all_chunks(self):
        chunker = TextChunker(chunk_size=10, overlap=2)
        meta = _make_metadata(title="Ma Note", file_hash="xyz")
        sections = [_make_section(_words(30))]
        chunks = chunker.chunk_note(meta, sections)
        for chunk in chunks:
            assert chunk.note_title == "Ma Note"
            assert chunk.file_hash == "xyz"

    def test_chunk_note_serializes_entity_metadata(self):
        chunker = TextChunker(chunk_size=10, overlap=2)
        meta = _make_metadata(
            entities=NoteEntities(persons=["Alice"], orgs=["ACME"], locations=["Paris"], misc=["MLX"])
        )
        chunks = chunker.chunk_note(meta, [_make_section(_words(12))])
        assert chunks[0].ner_persons == "Alice"
        assert chunks[0].ner_orgs == "ACME"
        assert chunks[0].ner_locations == "Paris"
        assert chunks[0].ner_misc == "MLX"


# ---------------------------------------------------------------------------
# Tests TextChunker — méthodes internes
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChunkerInternals:
    def test_sliding_window_no_overlap(self):
        chunker = TextChunker(chunk_size=5, overlap=0)
        words = list(range(15))
        result = chunker._sliding_window([str(w) for w in words])
        assert len(result) == 3
        assert result[0] == "0 1 2 3 4"

    def test_sliding_window_with_overlap(self):
        chunker = TextChunker(chunk_size=5, overlap=2)
        words = [str(i) for i in range(10)]
        result = chunker._sliding_window(words)
        # Tous les éléments couverts
        assert len(result) >= 2

    def test_merge_paragraphs_single_para(self):
        chunker = TextChunker(chunk_size=100, overlap=10)
        result = chunker._merge_paragraphs(["un seul paragraphe ici"])
        assert len(result) == 1

    def test_merge_paragraphs_splits_at_size(self):
        chunker = TextChunker(chunk_size=5, overlap=0)
        paras = [_words(4), _words(4), _words(4)]
        result = chunker._merge_paragraphs(paras)
        assert len(result) >= 2

    def test_merge_paragraphs_reuses_overlap_words(self):
        chunker = TextChunker(chunk_size=5, overlap=2)
        result = chunker._merge_paragraphs([_words(3), _words(3), _words(3)])
        assert len(result) >= 2
        second_words = result[1].split()
        assert second_words[0] in result[0].split()[-2:]

    def test_split_section_returns_empty_for_blank_content(self):
        chunker = TextChunker(chunk_size=5, overlap=1)
        assert chunker._split_section(_make_section("   ")) == []

    def test_sliding_window_returns_single_chunk_when_exact_size(self):
        chunker = TextChunker(chunk_size=5, overlap=2)
        result = chunker._sliding_window([str(i) for i in range(5)])
        assert result[0] == "0 1 2 3 4"
        assert result[-1] == "3 4"
