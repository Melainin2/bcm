"""Retriever hybride : recherche sémantique (dense) + boost lexical.

La recherche dense seule (embeddings BGE) échoue sur les identifiants rares
comme les codes d'erreur (ex. ORA-01555) : le token est trop spécifique pour
dominer le vecteur. On récupère donc un pool élargi de candidats, puis on
re-classe en ajoutant un bonus lexical (mots-clés de la question + correspondance
exacte des codes d'erreur). Cela fonctionne aussi en multilingue, car un code
comme « ORA-01555 » apparaît tel quel dans une question arabe ou française.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

import config
from rag import embeddings
from rag.vectorstore import VectorStore

logger = logging.getLogger(__name__)

# Codes d'erreur SGBD : ORA-01555, PLS-00201, TNS-12154, RMAN-06059, PG-... etc.
ERROR_CODE_RE = re.compile(r"\b(?:ORA|PLS|TNS|RMAN|IMP|EXP|PG)-?\d{3,5}\b", re.IGNORECASE)

_STOPWORDS = {
    "the", "what", "how", "can", "are", "and", "for", "you", "with", "that",
    "this", "when", "why", "does", "from", "your", "use", "using", "una", "les",
    "des", "est", "que", "qui", "comment", "quoi", "dans", "pour", "avec", "une",
}

# Poids du bonus lexical dans le re-classement.
CODE_BONUS = 0.30      # correspondance exacte d'un code d'erreur
KEYWORD_BONUS = 0.12   # proportion de mots-clés de la question présents


def _code_variants(code: str) -> Set[str]:
    """Génère les formes possibles d'un code : ORA-01555 et ORA01555."""
    upper = code.upper()
    no_sep = re.sub(r"[-\s]", "", upper)
    m = re.match(r"([A-Z]+)(\d+)", no_sep)
    variants = {upper, no_sep}
    if m:
        variants.add(f"{m.group(1)}-{m.group(2)}")
    return variants


def _extract_terms(question: str) -> Tuple[Set[str], Set[str]]:
    """Retourne (codes d'erreur normalisés sans séparateur, mots-clés)."""
    codes = {
        m.group(0).upper().replace("-", "") for m in ERROR_CODE_RE.finditer(question)
    }
    words = re.findall(r"[A-Za-z_]{3,}", question.lower())
    terms = {w for w in words if w not in _STOPWORDS}
    return codes, terms


def _raw_codes(question: str) -> Set[str]:
    """Codes d'erreur tels qu'ils apparaissent, avec toutes leurs variantes."""
    variants: Set[str] = set()
    for m in ERROR_CODE_RE.finditer(question):
        variants |= _code_variants(m.group(0))
    return variants


def _lexical_bonus(text: str, codes: Set[str], terms: Set[str]) -> float:
    bonus = 0.0
    if codes:
        haystack = re.sub(r"[-\s]", "", text.upper())
        for code in codes:
            if code in haystack:
                bonus += CODE_BONUS
    if terms:
        low = text.lower()
        hits = sum(1 for w in terms if w in low)
        bonus += KEYWORD_BONUS * (hits / len(terms))
    return bonus


class Retriever:
    def __init__(self, store: Optional[VectorStore] = None) -> None:
        self.store = store or VectorStore()

    def retrieve(self, question: str, top_k: Optional[int] = None) -> List[Dict]:
        """Retourne les top-k passages les plus pertinents (dense + lexical)."""
        k = top_k or config.TOP_K
        vector = embeddings.embed_query(question)

        # Pool élargi de candidats pour laisser le re-classement lexical opérer.
        pool_size = max(k * 10, 50)
        candidates = self.store.query(vector, pool_size)

        # Garde-fou codes d'erreur : force l'entrée des chunks contenant le code
        # exact dans le pool (sinon ils restent hors du top dense).
        seen = {p["source_id"] for p in candidates}
        for code in _raw_codes(question):
            for p in self.store.query_contains(vector, max(k * 3, 15), code):
                if p["source_id"] not in seen:
                    seen.add(p["source_id"])
                    candidates.append(p)

        if not candidates:
            return []

        codes, terms = _extract_terms(question)
        for p in candidates:
            dense = p.get("score") or 0.0
            p["_rank"] = dense + _lexical_bonus(p.get("text", ""), codes, terms)

        candidates.sort(key=lambda p: p["_rank"], reverse=True)
        top = candidates[:k]
        for p in top:
            p.pop("_rank", None)

        logger.info(
            "Question : %r -> %d passage(s) (pool=%d, codes=%s)",
            question[:60], len(top), len(candidates), codes or "-",
        )
        return top
