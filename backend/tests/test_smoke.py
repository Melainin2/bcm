"""Test de fumée : valide le câblage complet sans télécharger de modèle ni
appeler l'API Claude (embeddings et Claude sont simulés).

Usage :
    cd backend
    python tests/test_smoke.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import tempfile  # noqa: E402

import config  # noqa: E402

# Isolation : le test utilise une base ChromaDB temporaire et une collection
# dédiée pour ne JAMAIS écraser la vraie base de production (store.reset()).
config.CHROMA_PATH = tempfile.mkdtemp(prefix="dbagpt_test_chroma_")
config.COLLECTION_NAME = "test_smoke"

from rag import embeddings  # noqa: E402
from rag.chunker import chunk_pages  # noqa: E402
from rag.loader import load_documents  # noqa: E402

DIM = 32


def _fake_vector(text: str):
    """Vecteur déterministe basé sur un hachage (pas de modèle ML nécessaire)."""
    h = hashlib.sha256(text.lower().encode()).digest()
    vals = [((h[i % len(h)] + i) % 97) / 97.0 for i in range(DIM)]
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]


def main() -> int:
    # 1. Simule les embeddings (sinon sentence-transformers serait requis).
    embeddings.embed_documents = lambda texts: [_fake_vector(t) for t in texts]
    embeddings.embed_query = lambda text: _fake_vector(text)

    from rag.vectorstore import VectorStore

    # 2. Ingestion en mémoire à partir des documents d'exemple.
    pages = load_documents(config.DATA_PATH)
    chunks = chunk_pages(pages, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    assert chunks, "Aucun chunk généré depuis data/"

    store = VectorStore()
    store.reset()
    store.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings.embed_documents([c.text for c in chunks]),
        documents=[c.text for c in chunks],
        metadatas=[
            {
                "filename": c.filename,
                "page": c.page,
                "chunk_id": c.chunk_id,
                "source_path": c.source_path,
            }
            for c in chunks
        ],
    )
    assert store.count() == len(chunks)
    print(f"[OK] Ingestion : {store.count()} chunks indexés.")

    # 3. Retriever sémantique.
    from rag.retriever import Retriever

    retriever = Retriever(store=store)
    passages = retriever.retrieve("VACUUM PostgreSQL", top_k=3)
    assert passages, "Le retriever n'a rien retourné."
    assert all("score" in p for p in passages)
    print(f"[OK] Retriever : {len(passages)} passages, top score={passages[0]['score']}.")

    # 4. Client Claude + reranker simulés + pipeline complet.
    from rag import reranker

    def _fake_rerank(question, passages, top_k=None):
        for p in passages:
            p["rerank_score"] = max(p.get("score") or 0.0, 0.5)
        return passages[: (top_k or config.TOP_K)]

    reranker.rerank = _fake_rerank

    class FakeClaude:
        def generate(self, question, passages, language="en"):
            return (f"Réponse simulée pour: {question}", passages)

    from rag.pipeline import RAGPipeline

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.retriever = retriever
    pipeline.claude = FakeClaude()
    config.SIMILARITY_THRESHOLD = 0.0  # garantit l'appel Claude dans le smoke test
    result = pipeline.answer("Comment fonctionne VACUUM ?", top_k=3)
    assert result["answer"].startswith("Réponse simulée")
    assert result["sources"] and result["sources"][0]["excerpt"]
    print(f"[OK] Pipeline : {len(result['sources'])} sources retournées.")

    # 5. API FastAPI via TestClient (health + source + validations chat).
    from fastapi.testclient import TestClient
    import main as api

    api._state["store"] = store  # injecte la base pré-remplie
    client = TestClient(api.app)

    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["documents_indexed"] == len(chunks)
    print(f"[OK] /api/health : {h['documents_indexed']} docs, modèle={h['model']}.")

    sid = chunks[0].id
    s = client.get(f"/api/source/{sid}").json()
    assert s["source_id"] == sid and s["text"]
    print(f"[OK] /api/source : source '{s['filename']}' ouverte (p.{s['page']}).")

    # Question hors documentation -> renvoie tout de même des passages (top-k),
    # c'est Claude qui refuserait ; on vérifie ici la validation d'entrée vide.
    bad = client.post("/api/chat", json={"question": ""})
    assert bad.status_code == 422
    print("[OK] /api/chat : question vide rejetée (422).")

    missing = client.get("/api/source/inexistant::p1::c0")
    assert missing.status_code == 404
    print("[OK] /api/source : identifiant inconnu -> 404.")

    print("\n✅ Tous les tests de fumée sont passés.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
