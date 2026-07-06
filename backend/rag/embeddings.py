"""Embeddings locaux normalisés, avec préfixes adaptés au modèle.

Supporte deux familles de modèles (auto-détectées d'après le nom) :
  - BGE   (BAAI/bge-*)          → instruction de requête « Represent this... »
  - E5    (intfloat/*e5*)       → préfixes obligatoires « query: » / « passage: »

C'est important : appliquer le mauvais préfixe dégrade fortement le retrieval,
en particulier pour e5 (multilingue) qui a été entraîné avec ces préfixes.
"""

from __future__ import annotations

import logging
from typing import List

import config

logger = logging.getLogger(__name__)

# Instruction recommandée par BGE pour les requêtes de recherche.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_model = None
_loaded_name = None


def _family(name: str) -> str:
    low = name.lower()
    if "e5" in low:
        return "e5"
    if "bge" in low:
        return "bge"
    return "generic"


def get_model():
    """Charge le modèle d'embedding une seule fois (singleton paresseux)."""
    global _model, _loaded_name
    if _model is None or _loaded_name != config.EMBEDDING_MODEL:
        from sentence_transformers import SentenceTransformer

        logger.info("Chargement du modèle d'embedding : %s", config.EMBEDDING_MODEL)
        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        _loaded_name = config.EMBEDDING_MODEL
    return _model


def _prefix_documents(texts: List[str]) -> List[str]:
    fam = _family(config.EMBEDDING_MODEL)
    if fam == "e5":
        return [f"passage: {t}" for t in texts]
    return texts  # BGE encode les passages sans instruction


def _prefix_query(text: str) -> str:
    fam = _family(config.EMBEDDING_MODEL)
    if fam == "e5":
        return f"query: {text}"
    if fam == "bge":
        return BGE_QUERY_INSTRUCTION + text
    return text


def embed_documents(texts: List[str]) -> List[List[float]]:
    """Encode des passages de documents (embeddings normalisés)."""
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        _prefix_documents(texts),
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return [v.tolist() for v in vectors]


def embed_query(text: str) -> List[float]:
    """Encode une question utilisateur avec le préfixe adapté au modèle."""
    model = get_model()
    vector = model.encode(
        [_prefix_query(text)],
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vector[0].tolist()
