"""Tests du retriever, du reranker (stubbé) et du pipeline complet (Claude stubbé)."""

import config
from rag.retriever import Retriever


def test_retriever_returns_scored_passages(populated_store):
    store, _ = populated_store
    r = Retriever(store=store)
    passages = r.retrieve("VACUUM PostgreSQL dead tuples", top_k=5)
    assert passages
    assert all("score" in p for p in passages)
    assert all("source_id" in p for p in passages)


def test_retriever_error_code_guardrail(populated_store):
    store, _ = populated_store
    r = Retriever(store=store)
    passages = r.retrieve("What is ORA-01555?", top_k=5)
    files = " ".join((p.get("filename") or "") for p in passages)
    # Le garde-fou lexical doit faire remonter la fiche undo/ora-01555.
    assert "ora01555" in files.lower() or "undo" in files.lower()


def test_reranker_is_applied(populated_store):
    """Le reranker stubbé ajoute rerank_score et reclasse."""
    from rag import reranker
    store, _ = populated_store
    r = Retriever(store=store)
    candidates = r.retrieve("autovacuum performance", top_k=15)
    top = reranker.rerank("autovacuum performance", candidates, top_k=5)
    assert len(top) <= 5
    assert all("rerank_score" in p for p in top)
    scores = [p["rerank_score"] for p in top]
    assert scores == sorted(scores, reverse=True)


def test_pipeline_answer_with_stubbed_claude(populated_store, monkeypatch):
    store, _ = populated_store
    from rag.pipeline import RAGPipeline

    pipe = RAGPipeline.__new__(RAGPipeline)
    pipe.retriever = Retriever(store=store)

    class FakeClaude:
        def generate(self, question, passages, language="en",
                     confidence="MEDIUM", model=None):
            return (f"[{language}] réponse simulée", passages)

    pipe.claude = FakeClaude()

    # Seuils bas pour garantir le passage du garde-fou avec le reranker stubbé.
    monkeypatch.setattr(config, "SIMILARITY_THRESHOLD", 0.01)
    monkeypatch.setattr(config, "MEDIUM_CONFIDENCE_THRESHOLD", 0.01)
    monkeypatch.setattr(config, "HIGH_CONFIDENCE_THRESHOLD", 0.5)
    res = pipe.answer("How does VACUUM reclaim space in PostgreSQL?", top_k=5)

    assert res["answer"].startswith("[")
    assert res["confidence"]["level"] in {"HIGH", "MEDIUM", "LOW"}
    assert 0.0 <= res["confidence"]["score"] <= 1.0
    assert "total_ms" in res["timing"]
    assert res["sources"]  # Claude appelé → sources renvoyées
    assert all(s["similarity"] >= config.SIMILARITY_THRESHOLD for s in res["sources"])
    assert "query_analysis" in res
    assert res["language"] == "en"


def test_pipeline_abstains_below_threshold(populated_store, monkeypatch):
    store, _ = populated_store
    from rag.pipeline import RAGPipeline

    pipe = RAGPipeline.__new__(RAGPipeline)
    pipe.retriever = Retriever(store=store)

    called = {"claude": False}

    class FakeClaude:
        def generate(self, question, passages, language="en",
                     confidence="MEDIUM", model=None):
            called["claude"] = True
            return ("should not be called", passages)

    pipe.claude = FakeClaude()

    # Seuil impossible : aucun chunk ne passe le filtre → court-circuit de Claude.
    monkeypatch.setattr(config, "SIMILARITY_THRESHOLD", 1.01)
    res = pipe.answer("What is the capital of France?", top_k=5)

    assert res["confidence"]["level"] == "LOW"
    assert called["claude"] is False
    assert res["sources"] == []
