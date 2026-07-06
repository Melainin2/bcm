"""Reranking par cross-encoder (BAAI/bge-reranker-base).

Le retriever dense/lexical renvoie un pool de candidats (top 15). Un cross-encoder
lit la paire (question, passage) *ensemble* et attribue un score de pertinence
bien plus fiable que la similarité cosinus. On garde ensuite le top 5 pour Claude.

Pipeline : question → retriever (top 15) → reranker → top 5 → Claude.

bge-reranker-base est multilingue : il reclasse correctement des passages anglais
pour une question arabe ou française.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

import config

logger = logging.getLogger(__name__)

_model = None
_loaded_name = None


def _sigmoid(x: float) -> float:
    # Le cross-encoder renvoie un logit ; on le ramène dans [0, 1] (probabilité).
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def get_model():
    """Charge le cross-encoder une seule fois (singleton paresseux)."""
    global _model, _loaded_name
    if _model is None or _loaded_name != config.RERANKER_MODEL:
        from sentence_transformers import CrossEncoder

        logger.info("Chargement du reranker : %s", config.RERANKER_MODEL)
        _model = CrossEncoder(config.RERANKER_MODEL, max_length=512)
        _loaded_name = config.RERANKER_MODEL
    return _model


def rerank(
    question: str, passages: List[Dict], top_k: Optional[int] = None
) -> List[Dict]:
    """Reclasse les passages par pertinence (question, passage) et garde top_k.

    Ajoute à chaque passage :
      - rerank_score : probabilité de pertinence [0, 1] (score principal de confiance)
    """
    if not passages:
        return []
    k = top_k or config.TOP_K
    if not config.RERANK_ENABLED:
        return passages[:k]

    model = get_model()
    pairs = [(question, p.get("text", "")) for p in passages]
    raw_scores = model.predict(pairs, show_progress_bar=False)

    for p, s in zip(passages, raw_scores):
        p["rerank_score"] = round(_sigmoid(float(s)), 4)

    passages.sort(key=lambda p: p.get("rerank_score", 0.0), reverse=True)
    top = passages[:k]
    logger.info(
        "Rerank : %d candidats → top %d (meilleur=%.3f)",
        len(passages), len(top), top[0]["rerank_score"] if top else 0.0,
    )
    return top
