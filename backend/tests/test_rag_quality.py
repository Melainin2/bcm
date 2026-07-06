"""Tests de QUALITÉ du RAG (intégration) — spec §11.

Ces tests utilisent les VRAIS modèles (embeddings + reranker) et la VRAIE base
ChromaDB indexée. Ils ne font PAS d'appel Claude : on vérifie le retrieval, le
filtre de pertinence, le reranking et la décision du garde-fou via `prepare()`.

Ils sont automatiquement ignorés si la base indexée est absente
(ex. CI sans ingestion). Lancer localement après `python scripts/ingest.py`.

Marqueurs : realmodels (pas de stub) + realindex (vraie base).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402

pytestmark = [pytest.mark.realmodels, pytest.mark.realindex]


@pytest.fixture(scope="module")
def pipeline():
    """Pipeline réel sur la base indexée. Skip si la base est vide/absente."""
    try:
        from rag.vectorstore import VectorStore
        store = VectorStore()
        if store.count() == 0:
            pytest.skip("ChromaDB vide — lancez d'abord scripts/ingest.py")
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"ChromaDB indisponible : {exc}")

    from rag.pipeline import RAGPipeline
    from rag.retriever import Retriever
    pipe = RAGPipeline.__new__(RAGPipeline)
    pipe.retriever = Retriever(store=store)
    pipe.claude = None  # jamais appelé : on n'utilise que prepare()
    return pipe


def _no_fake_sources(prep):
    """Invariant global : aucune source sous le seuil de similarité, jamais 0 %."""
    for p in prep["passages"]:
        sim = p.get("score") or 0.0
        assert sim >= config.SIMILARITY_THRESHOLD, f"source sous seuil: {sim}"
        assert sim > 0.0, "similarité 0 % interdite"


# 1. Oracle tablespace → HIGH, sources non vides.
def test_tablespace_high_confidence(pipeline):
    prep = pipeline.prepare("What is a tablespace in Oracle?")
    assert prep["decision"] == "CALL_CLAUDE"
    assert prep["confidence"] == "HIGH"
    assert prep["passages"], "sources attendues non vides"
    assert prep["relevance"] >= config.HIGH_CONFIDENCE_THRESHOLD
    _no_fake_sources(prep)


# 2. ORA-01555 (français) → MEDIUM/HIGH, sources pertinentes contenant UNDO.
def test_ora01555_undo(pipeline):
    prep = pipeline.prepare("Comment résoudre ORA-01555 ?")
    assert prep["decision"] == "CALL_CLAUDE"
    assert prep["confidence"] in {"MEDIUM", "HIGH"}
    assert prep["passages"]
    blob = " ".join(p.get("text", "").upper() for p in prep["passages"])
    assert "UNDO" in blob  # UNDO ou UNDO_RETENTION présents dans le contexte
    _no_fake_sources(prep)


# 3. Arabe « trouver les requêtes lentes » → sources pertinentes OU vides,
#    mais JAMAIS une source de similarité < seuil / 0 %.
def test_arabic_slow_queries(pipeline):
    prep = pipeline.prepare("كيف أجد الاستعلامات البطيئة؟")
    assert prep["language"] == "ar"
    if prep["decision"] == "CALL_CLAUDE":
        assert prep["passages"]
        _no_fake_sources(prep)
    else:
        assert prep["passages"] == []  # abstention propre, aucune fausse source


# 4. Hors domaine (Lionel Messi) → LOW, sources vides, Claude non appelé.
def test_out_of_domain_messi(pipeline):
    prep = pipeline.prepare("What is Lionel Messi?")
    assert prep["decision"] == "NO_RELEVANT_SOURCE"
    assert prep["confidence"] == "LOW"
    assert prep["passages"] == []


# 5. Acronyme mal orthographié « ARW » → suggestion/correction vers AWR, pas d'hallucination.
def test_arw_suggests_awr(pipeline):
    prep = pipeline.prepare("What is ARW?")
    norm = prep["norm"]
    suggested = {s[1].upper() for s in norm.suggestions}
    corrected = (norm.corrected or "").upper()
    assert "AWR" in suggested or "AWR" in corrected, "ARW doit mener à AWR"
    # Pas d'hallucination : si aucune source fiable, on n'invente pas.
    if prep["decision"] == "NO_RELEVANT_SOURCE":
        assert prep["passages"] == []
    else:
        _no_fake_sources(prep)
