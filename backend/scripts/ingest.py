"""Script d'ingestion : reconstruit la base vectorielle ChromaDB depuis data/.

Usage :
    cd backend
    python scripts/ingest.py           # reconstruit la base (reset par défaut)
    python scripts/ingest.py --reset   # idem, explicite (recommandé)
    python scripts/ingest.py --keep    # ajoute sans réinitialiser
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Permet d'importer config/ et rag/ quand on lance le script directement.
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from rag import embeddings  # noqa: E402
from rag.chunker import chunk_pages  # noqa: E402
from rag.loader import count_files_by_db_type, load_documents  # noqa: E402
from rag.vectorstore import VectorStore  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ingest")

BATCH_SIZE = 64


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestion DBA-GPT")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Ne pas réinitialiser la collection avant d'ajouter (ajout incrémental).",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Réinitialiser explicitement la collection (comportement par défaut).",
    )
    args = parser.parse_args()
    # Reset par défaut ; --keep désactive le reset ; --reset le force (explicite).
    do_reset = not args.keep

    logger.info("Dossier de données : %s", config.DATA_PATH)
    logger.info("Base ChromaDB      : %s", config.CHROMA_PATH)

    # --- Diagnostic : fichiers présents sur disque, par type de base ---------
    counts = count_files_by_db_type(config.DATA_PATH)
    logger.info("Found Oracle files:     %d", counts["oracle"])
    logger.info("Found PostgreSQL files: %d", counts["postgresql"])
    logger.info("Found logs files:       %d", counts["logs"])
    if counts["unknown"]:
        logger.info("Found unknown files:    %d", counts["unknown"])
    logger.info("Total files found:      %d", counts["total"])

    pages = load_documents(config.DATA_PATH)
    if not pages:
        logger.warning(
            "Aucun document trouvé dans %s. "
            "Ajoutez des fichiers PDF/TXT/LOG/MD puis relancez.",
            config.DATA_PATH,
        )
        return 1

    chunks = chunk_pages(pages, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    logger.info("Chunks generated:       %d", len(chunks))
    if not chunks:
        logger.warning("Aucun chunk généré (documents vides ?).")
        return 1

    store = VectorStore()
    logger.info("Chroma documents before reset: %d", store.count())
    if do_reset:
        logger.info("Réinitialisation de la collection (--reset)...")
        store.reset()
        logger.info("Chroma documents after reset:  %d", store.count())

    # Horodatage d'indexation commun à tout le lot (stocké sur chaque chunk).
    indexed_at = datetime.now(timezone.utc).isoformat()

    logger.info("Calcul des embeddings et indexation (par lots de %d)...", BATCH_SIZE)
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        vectors = embeddings.embed_documents([c.text for c in batch])
        store.add(
            ids=[c.id for c in batch],
            embeddings=vectors,
            documents=[c.text for c in batch],
            metadatas=[
                {
                    "filename": c.filename,
                    "page": c.page,
                    "chunk_id": c.chunk_id,
                    "source_path": c.source_path,
                    "title": c.title,
                    "section": c.section,
                    "db_type": c.db_type,
                    "file_type": c.file_type,
                    "indexed_at": indexed_at,
                }
                for c in batch
            ],
        )
        logger.info("  Indexé %d / %d", min(i + BATCH_SIZE, len(chunks)), len(chunks))

    logger.info("Chroma documents after ingestion: %d", store.count())
    logger.info("✅ Terminé. %d chunks dans la collection '%s'.",
                store.count(), config.COLLECTION_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
