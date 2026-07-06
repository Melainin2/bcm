"""Tests du chunking récursif et des métadonnées."""

from rag.chunker import Chunk, chunk_pages, chunk_text
from rag.loader import LoadedPage


def test_chunk_text_respects_size():
    text = "mot " * 500  # ~2000 caractères
    chunks = chunk_text(text, chunk_size=700, overlap=150)
    assert len(chunks) > 1
    assert all(len(c) <= 700 + 200 for c in chunks)  # tolérance overlap/merge


def test_chunk_text_short_returns_single():
    assert chunk_text("court", 700, 150) == ["court"]


def test_chunk_text_empty():
    assert chunk_text("   ", 700, 150) == []


def test_recursive_split_prefers_paragraphs():
    text = "Para one sentence.\n\nPara two sentence.\n\nPara three sentence." * 20
    chunks = chunk_text(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1


def test_markdown_section_and_title_metadata():
    md = (
        "# VACUUM\nVACUUM reclaims storage occupied by dead tuples.\n\n"
        "## Autovacuum\nAutovacuum automates VACUUM.\n"
    )
    page = LoadedPage(text=md, filename="postgresql_vacuum.md", page=1,
                      source_path="postgresql/postgresql_vacuum.md")
    chunks = chunk_pages([page], chunk_size=700, overlap=150)
    assert chunks
    titles = {c.title for c in chunks}
    assert "VACUUM" in titles or "Autovacuum" in titles
    # chunk_id doit être unique et croissant par page.
    ids = [c.chunk_id for c in chunks]
    assert ids == sorted(ids)


def test_chunk_has_all_metadata_fields():
    page = LoadedPage(text="x " * 400, filename="f.md", page=3, source_path="a/f.md")
    chunks = chunk_pages([page], 300, 60)
    c = chunks[0]
    assert isinstance(c, Chunk)
    for field in ("id", "text", "filename", "page", "chunk_id", "source_path",
                  "title", "section"):
        assert hasattr(c, field)
    assert c.page == 3
    assert c.source_path == "a/f.md"
    assert c.id.startswith("a/f.md::p3::c")
