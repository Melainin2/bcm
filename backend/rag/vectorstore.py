"""Interface avec ChromaDB (stockage vectoriel persistant)."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import chromadb

import config

logger = logging.getLogger(__name__)


class VectorStore:
    """Wrapper autour d'une collection ChromaDB persistante."""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path=config.CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "ChromaDB prêt (%s) - collection '%s' (%d chunks)",
            config.CHROMA_PATH,
            config.COLLECTION_NAME,
            self.count(),
        )

    def count(self) -> int:
        return self.collection.count()

    def reset(self) -> None:
        """Supprime et recrée la collection (reconstruction complète)."""
        try:
            self.client.delete_collection(config.COLLECTION_NAME)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=config.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict],
    ) -> None:
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, embedding: List[float], top_k: int) -> List[Dict]:
        """Recherche sémantique : retourne les meilleurs chunks + score."""
        if self.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self.count()),
            include=["documents", "metadatas", "distances"],
        )
        return self._format(result)

    def query_contains(
        self, embedding: List[float], top_k: int, substring: str
    ) -> List[Dict]:
        """Recherche dense restreinte aux chunks contenant `substring` (exact).

        Sert de garde-fou lexical pour les identifiants rares (codes d'erreur)
        que la recherche dense seule ne fait pas remonter.
        """
        if self.count() == 0:
            return []
        try:
            result = self.collection.query(
                query_embeddings=[embedding],
                n_results=min(top_k, self.count()),
                where_document={"$contains": substring},
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("query_contains a échoué pour %r : %s", substring, exc)
            return []
        return self._format(result)

    def get_by_id(self, source_id: str) -> Optional[Dict]:
        """Récupère un chunk précis par son identifiant (ouverture de source)."""
        result = self.collection.get(
            ids=[source_id],
            include=["documents", "metadatas"],
        )
        if not result["ids"]:
            return None
        meta = result["metadatas"][0] or {}
        return {
            "source_id": result["ids"][0],
            "text": result["documents"][0],
            "filename": meta.get("filename"),
            "page": meta.get("page"),
            "chunk_id": meta.get("chunk_id"),
            "source_path": meta.get("source_path"),
            "title": meta.get("title", ""),
            "section": meta.get("section", ""),
        }

    @staticmethod
    def _format(result: Dict) -> List[Dict]:
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]

        passages: List[Dict] = []
        for i, doc in enumerate(docs):
            meta = metas[i] or {}
            distance = dists[i] if i < len(dists) else None
            # Distance cosinus -> similarité (1 = identique).
            similarity = None if distance is None else round(1.0 - distance, 4)
            passages.append(
                {
                    "source_id": ids[i],
                    "text": doc,
                    "filename": meta.get("filename"),
                    "page": meta.get("page"),
                    "chunk_id": meta.get("chunk_id"),
                    "source_path": meta.get("source_path"),
                    "title": meta.get("title", ""),
                    "section": meta.get("section", ""),
                    "score": similarity,
                }
            )
        return passages
