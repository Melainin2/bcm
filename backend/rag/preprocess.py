"""Compatibilité rétro : `preprocess` délègue désormais à `query_normalizer`.

L'ancienne API `analyze_query()` / `QueryAnalysis` est conservée pour ne casser
aucun import existant. La logique vit dans `rag/query_normalizer.py`.
"""

from __future__ import annotations

from rag.query_normalizer import (  # noqa: F401
    ACRONYMS,
    COMMON_TYPOS,
    DOMAIN_VOCAB,
    QueryNormalization,
    normalize_query,
)

# Alias historique.
QueryAnalysis = QueryNormalization


def analyze_query(question: str) -> QueryNormalization:
    """Alias rétrocompatible de normalize_query()."""
    return normalize_query(question)
