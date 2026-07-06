"""Statistiques système : fichiers présents sur disque vs chunks réellement indexés.

Deux sources de vérité distinctes, volontairement séparées pour diagnostiquer les
écarts d'ingestion :
  A. FICHIERS SUR DISQUE  — ce qui existe dans data/ (indépendant de ChromaDB).
  B. INDEXÉ DANS CHROMADB — ce qui a réellement été vectorisé (chunks + fichiers).

Si (A) > (B) pour un type de base, c'est qu'une ré-ingestion est nécessaire :
un avertissement est renvoyé (ex. « PostgreSQL files detected but not indexed »).
Aucune valeur n'est inventée.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config
from rag.loader import (
    PDF_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    detect_db_type,
)

_LOG_EXTENSIONS = {".log"}
_TXT_EXTENSIONS = {".txt"}
_MD_EXTENSIONS = {".md"}

_DB_TYPES = ("oracle", "postgresql", "logs", "unknown")


def _last_indexed_at(chroma_path: str) -> Optional[str]:
    """Date de dernière modification de la base ChromaDB (ISO 8601), si dispo."""
    base = Path(chroma_path)
    if not base.exists():
        return None
    latest = 0.0
    for p in base.rglob("*"):
        try:
            latest = max(latest, p.stat().st_mtime)
        except OSError:
            continue
    if latest <= 0:
        latest = base.stat().st_mtime
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()


def compute_file_stats(data_path: str) -> Dict[str, int]:
    """A. Compte les FICHIERS présents dans data/, par extension et par db_type."""
    root = Path(data_path)
    stats = {
        "total_files": 0,
        "pdf_count": 0,
        "txt_count": 0,
        "log_count": 0,
        "md_count": 0,
        "oracle_files": 0,
        "postgresql_files": 0,
        "logs_files": 0,
        "unknown_files": 0,
    }
    if not root.exists():
        return stats

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        stats["total_files"] += 1
        if ext in PDF_EXTENSIONS:
            stats["pdf_count"] += 1
        elif ext in _TXT_EXTENSIONS:
            stats["txt_count"] += 1
        elif ext in _LOG_EXTENSIONS:
            stats["log_count"] += 1
        elif ext in _MD_EXTENSIONS:
            stats["md_count"] += 1

        rel = str(path.relative_to(root))
        stats[f"{detect_db_type(rel)}_files"] += 1

    return stats


def compute_index_stats(store) -> Dict[str, int]:
    """B. Compte les CHUNKS et FICHIERS réellement indexés dans ChromaDB, par db_type.

    Le db_type provient des métadonnées si présentes, sinon il est déduit du
    source_path (rétrocompatible avec un index construit avant l'ajout du champ).
    """
    stats = {
        "total_indexed_chunks": 0,
        "indexed_files_count": 0,
    }
    for db in _DB_TYPES:
        stats[f"indexed_{db}_chunks"] = 0
        stats[f"indexed_{db}_files"] = 0

    if store is None or store.count() == 0:
        return stats

    try:
        result = store.collection.get(include=["metadatas"])
    except Exception:
        return stats

    metas = result.get("metadatas") or []
    files_by_type: Dict[str, set] = {db: set() for db in _DB_TYPES}
    all_files: set = set()

    for meta in metas:
        meta = meta or {}
        source_path = meta.get("source_path") or ""
        db = meta.get("db_type") or detect_db_type(source_path)
        if db not in _DB_TYPES:
            db = "unknown"
        stats["total_indexed_chunks"] += 1
        stats[f"indexed_{db}_chunks"] += 1
        if source_path:
            files_by_type[db].add(source_path)
            all_files.add(source_path)

    stats["indexed_files_count"] = len(all_files)
    for db in _DB_TYPES:
        stats[f"indexed_{db}_files"] = len(files_by_type[db])
    return stats


def _build_warnings(files: Dict, indexed: Dict) -> List[str]:
    """Signale les types de base présents sur disque mais absents de l'index."""
    warnings: List[str] = []
    labels = {"oracle": "Oracle", "postgresql": "PostgreSQL", "logs": "Logs"}
    for db, label in labels.items():
        on_disk = files.get(f"{db}_files", 0)
        indexed_files = indexed.get(f"indexed_{db}_files", 0)
        if on_disk > 0 and indexed_files < on_disk:
            warnings.append(
                f"{label} files detected ({on_disk}) but only {indexed_files} "
                f"indexed. Run: python scripts/ingest.py --reset"
            )
    return warnings


def build_stats(store) -> Dict:
    """Assemble la réponse complète de /api/stats (fichiers + index + config)."""
    files = compute_file_stats(config.DATA_PATH)
    indexed = compute_index_stats(store)
    total_chunks = store.count() if store is not None else 0

    return {
        "rag_ready": bool(store is not None and total_chunks > 0),
        # A. Fichiers sur disque -------------------------------------------
        "files": files,
        # B. Indexé dans ChromaDB ------------------------------------------
        "indexed": indexed,
        # Alias plat de compatibilité (utilisé par l'ancien affichage) ------
        "total_chunks": total_chunks,
        # Modèles & config --------------------------------------------------
        "embedding_model": config.EMBEDDING_MODEL,
        "claude_model": config.CLAUDE_MODEL,
        "available_claude_models": config.AVAILABLE_CLAUDE_MODELS,
        "chroma_path": config.CHROMA_PATH,
        "data_path": config.DATA_PATH,
        "collection_name": config.COLLECTION_NAME,
        "top_k": config.RERANK_TOP_K,
        "retriever_top_k": config.RETRIEVER_TOP_K,
        "similarity_threshold": config.SIMILARITY_THRESHOLD,
        "reranker_enabled": config.USE_RERANKER,
        "reranker_model": config.RERANKER_MODEL if config.USE_RERANKER else None,
        "last_indexed_at": _last_indexed_at(config.CHROMA_PATH),
        # Diagnostic --------------------------------------------------------
        "warnings": _build_warnings(files, indexed),
    }
