"""Orchestration du pipeline RAG production.

Pipeline (obligatoire) :
    question
      → normalisation (acronymes DBA + fautes de frappe)   [query_normalizer.py]
      → détection de langue (ar/fr/en)                      [lang.py]
      → embedding de la requête enrichie                    [embeddings.py]
      → ChromaDB : top RETRIEVER_TOP_K candidats            [retriever.py]
      → FILTRE : similarité dense ≥ SIMILARITY_THRESHOLD
      → si AUCUN candidat pertinent → PAS d'appel Claude, sources = [], LOW
      → reranker cross-encoder → RERANK_TOP_K               [reranker.py]
      → confiance (HIGH/MEDIUM/LOW) ; si LOW → PAS d'appel Claude
      → génération Claude (ancrée dans le contexte)         [claude_client.py]

Chaque étape est chronométrée. Aucune source de similarité < seuil n'est jamais
renvoyée ; aucune source « fake » n'est affichée.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

import config
from rag import lang, query_normalizer, reranker
from rag.claude_client import ClaudeClient, no_context_message
from rag.retriever import Retriever

logger = logging.getLogger("dba-gpt.rag")


def _confidence_level(score: float) -> str:
    if score >= config.HIGH_CONFIDENCE_THRESHOLD:
        return "HIGH"
    if score >= config.MEDIUM_CONFIDENCE_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def _relevance_score(passages: List[Dict]) -> float:
    """Score de pertinence du meilleur passage pour la confiance.

    Avec reranker : score du cross-encoder (discriminant, multilingue avec
    bge-reranker). Sans reranker : similarité dense.
    """
    if not passages:
        return 0.0
    top = passages[0]
    if config.USE_RERANKER and top.get("rerank_score") is not None:
        return float(top["rerank_score"])
    return float(top.get("score") or 0.0)


class RAGPipeline:
    """Assemble normalisation, retriever, filtre, reranker et client Claude."""

    def __init__(self) -> None:
        self.retriever = Retriever()
        self.claude = ClaudeClient()

    @property
    def store(self):
        return self.retriever.store

    def prepare(self, question: str, top_k: Optional[int] = None) -> Dict:
        """Exécute tout le RAG SAUF l'appel Claude (retrieval → filtre → rerank → gate).

        Utile pour les tests de qualité (sans coût LLM) et réutilisé par answer().
        Retourne : decision, passages, language, confidence, relevance, norm,
        top_similarity, timings.
        """
        rerank_k = top_k or config.RERANK_TOP_K
        timings: Dict[str, float] = {"retrieval_ms": 0.0, "rerank_ms": 0.0,
                                     "claude_ms": 0.0, "total_ms": 0.0}

        norm = query_normalizer.normalize_query(question)
        language = lang.detect_language(question)

        t = time.perf_counter()
        candidates = self.retriever.retrieve(norm.expanded, config.RETRIEVER_TOP_K)
        timings["retrieval_ms"] = round((time.perf_counter() - t) * 1000, 1)
        top_similarity = round(float(candidates[0].get("score") or 0.0), 4) if candidates else 0.0

        # FILTRE de pertinence : similarité dense ≥ seuil.
        relevant = [p for p in candidates
                    if (p.get("score") or 0.0) >= config.SIMILARITY_THRESHOLD]

        base = {"norm": norm, "language": language, "top_similarity": top_similarity,
                "timings": timings}

        if not relevant:
            return {**base, "decision": "NO_RELEVANT_SOURCE", "passages": [],
                    "confidence": "LOW", "relevance": top_similarity}

        t = time.perf_counter()
        passages = reranker.rerank(norm.corrected, relevant, top_k=rerank_k)
        timings["rerank_ms"] = round((time.perf_counter() - t) * 1000, 1)

        relevance = _relevance_score(passages)
        confidence = _confidence_level(relevance)

        if confidence == "LOW":
            return {**base, "decision": "NO_RELEVANT_SOURCE", "passages": [],
                    "confidence": "LOW", "relevance": round(relevance, 4)}

        return {**base, "decision": "CALL_CLAUDE", "passages": passages,
                "confidence": confidence, "relevance": round(relevance, 4)}

    def answer(
        self, question: str, top_k: Optional[int] = None, model: Optional[str] = None
    ) -> Dict:
        """Répond à une question et renvoie le format de réponse complet.

        `model` surcharge le modèle Claude par défaut (validé en amont côté API).
        """
        used_model = model or config.CLAUDE_MODEL
        t_total = time.perf_counter()
        prep = self.prepare(question, top_k)
        norm, language = prep["norm"], prep["language"]
        timings = prep["timings"]

        if prep["decision"] == "NO_RELEVANT_SOURCE":
            timings["total_ms"] = round((time.perf_counter() - t_total) * 1000, 1)
            self._log(question, norm, language, prep["top_similarity"], 0,
                      timings, "NO_RELEVANT_SOURCE")
            return self._empty(question, norm, language, prep["relevance"],
                               timings, used_model)

        passages, confidence = prep["passages"], prep["confidence"]
        t = time.perf_counter()
        answer, used = self.claude.generate(
            question, passages, language, confidence, model=used_model
        )
        timings["claude_ms"] = round((time.perf_counter() - t) * 1000, 1)
        timings["total_ms"] = round((time.perf_counter() - t_total) * 1000, 1)

        self._log(question, norm, language, prep["top_similarity"], len(passages),
                  timings, "CALL_CLAUDE")
        return self._build(answer, used, language, confidence,
                           prep["relevance"], norm, timings, used_model)

    # --- Helpers -------------------------------------------------------------
    @staticmethod
    def _sources(passages: List[Dict]) -> List[Dict]:
        out = []
        for p in passages:
            # Garde-fou ultime : jamais de source sous le seuil de similarité.
            if (p.get("score") or 0.0) < config.SIMILARITY_THRESHOLD:
                continue
            sid = p["source_id"]
            out.append({
                "id": sid,
                "filename": p.get("filename"),
                "page": p.get("page"),
                "section": p.get("title") or p.get("section") or "",
                "similarity": round(float(p.get("score") or 0.0), 4),
                "rerank_score": (round(float(p["rerank_score"]), 4)
                                 if p.get("rerank_score") is not None else None),
                "excerpt": p.get("text", ""),
                "source_url": f"/api/source/{sid}",
                "source_path": p.get("source_path"),
            })
        return out

    def _build(self, answer, passages, language, confidence, score,
               norm, timings, model) -> Dict:
        return {
            "answer": answer,
            "language": language,
            "confidence": {"level": confidence, "score": score},
            "corrected_query": norm.corrected_query,
            "sources": self._sources(passages),
            "timing": timings,
            "query_analysis": norm.as_dict(),
            "model": model,
        }

    def _empty(self, question, norm, language, score, timings, model) -> Dict:
        return {
            "answer": no_context_message(language),
            "language": language,
            "confidence": {"level": "LOW", "score": score},
            "corrected_query": norm.corrected_query,
            "sources": [],
            "timing": timings,
            "query_analysis": norm.as_dict(),
            "model": model,
        }

    @staticmethod
    def _log(question, norm, language, top_sim, n_sources, timings, decision):
        logger.info(
            "Q=%r | corrigée=%r | langue=%s | top_sim=%.3f | sources=%d | "
            "retrieval=%.0fms rerank=%.0fms claude=%.0fms total=%.0fms | %s",
            question[:80], (norm.corrected_query or norm.original)[:80], language,
            top_sim, n_sources, timings["retrieval_ms"], timings["rerank_ms"],
            timings["claude_ms"], timings["total_ms"], decision,
        )
