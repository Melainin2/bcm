"""Fixtures pytest partagées.

Objectif : tester TOUTE la logique RAG SANS télécharger de modèle ni appeler
Claude. On isole ChromaDB dans un dossier temporaire et on injecte des embeddings
et un reranker déterministes (basés sur un hachage).
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402

DIM = 48


def fake_vector(text: str):
    """Vecteur normalisé déterministe (aucun modèle ML requis)."""
    h = hashlib.sha256(text.lower().encode()).digest()
    vals = [((h[i % len(h)] + i) % 97) / 97.0 for i in range(DIM)]
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]


@pytest.fixture(autouse=True)
def isolate_chroma(request):
    """Redirige ChromaDB vers une base temporaire (jamais la prod).

    Les tests marqués `realindex` utilisent la vraie base indexée.
    """
    if request.node.get_closest_marker("realindex"):
        yield
        return
    saved = (config.CHROMA_PATH, config.COLLECTION_NAME)
    config.CHROMA_PATH = tempfile.mkdtemp(prefix="dbagpt_pytest_")
    config.COLLECTION_NAME = "pytest_docs"
    yield
    config.CHROMA_PATH, config.COLLECTION_NAME = saved


@pytest.fixture(autouse=True)
def stub_models(request, monkeypatch):
    """Remplace embeddings et reranker par des versions déterministes.

    Les tests marqués `realmodels` gardent les vrais modèles (intégration).
    """
    if request.node.get_closest_marker("realmodels"):
        return
    from rag import embeddings, reranker

    monkeypatch.setattr(embeddings, "embed_documents",
                        lambda texts: [fake_vector(t) for t in texts])
    monkeypatch.setattr(embeddings, "embed_query", lambda text: fake_vector(text))

    def fake_rerank(question, passages, top_k=None):
        # Score = recouvrement lexical simple, borné à [0, 1].
        qwords = set(question.lower().split())
        for p in passages:
            twords = set(p.get("text", "").lower().split())
            overlap = len(qwords & twords) / (len(qwords) or 1)
            p["rerank_score"] = round(min(overlap * 2, 0.99), 4)
        passages.sort(key=lambda p: p["rerank_score"], reverse=True)
        return passages[: (top_k or config.TOP_K)]

    monkeypatch.setattr(reranker, "rerank", fake_rerank)


@pytest.fixture
def sample_pages():
    """Pages d'exemple — uniquement les fichiers texte/markdown (rapide, déterministe).

    On NE parse PAS les gros PDF Oracle (3 400+ pages) : pypdf les rendrait très
    lents. On lit directement les .md/.log/.txt du corpus, qui couvrent VACUUM,
    tablespaces, ORA-01555 et performance — suffisant pour valider chunking,
    retriever, reranker et pipeline.
    """
    from pathlib import Path

    from rag.loader import (
        TEXT_EXTENSIONS, _read_text_file, LoadedPage,
        detect_db_type, detect_file_type,
    )

    data_root = Path(config.DATA_PATH).resolve()
    pages = []
    for path in sorted(data_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        text = _read_text_file(path)
        if text.strip():
            rel = str(path.relative_to(data_root))
            pages.append(LoadedPage(
                text=text, filename=path.name, page=1,
                source_path=rel, db_type=detect_db_type(rel),
                file_type=detect_file_type(path.name),
            ))
    return pages


@pytest.fixture
def populated_store(sample_pages):
    """Une VectorStore remplie avec les documents d'exemple (embeddings factices)."""
    from rag import embeddings
    from rag.chunker import chunk_pages
    from rag.vectorstore import VectorStore

    chunks = chunk_pages(sample_pages, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    store = VectorStore()
    store.reset()
    store.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings.embed_documents([c.text for c in chunks]),
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "filename": c.filename, "page": c.page, "chunk_id": c.chunk_id,
                "source_path": c.source_path, "title": c.title,
                "section": c.section, "db_type": c.db_type,
                "file_type": c.file_type, "indexed_at": "2026-07-05T00:00:00+00:00",
            }
            for c in chunks
        ],
    )
    return store, chunks
