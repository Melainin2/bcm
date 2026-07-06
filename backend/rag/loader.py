"""Chargement des documents locaux (PDF / TXT / LOG / MD) depuis le dossier data/."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".log", ".md"}
PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS


def detect_db_type(source_path: str) -> str:
    """Déduit le type de base à partir du dossier de rangement du document.

    data/oracle/...     -> "oracle"
    data/postgresql/... -> "postgresql"
    data/logs/...       -> "logs"
    sinon               -> "unknown"
    """
    parts = {p.lower() for p in Path(source_path).parts}
    if "oracle" in parts:
        return "oracle"
    if "postgresql" in parts:
        return "postgresql"
    if "logs" in parts:
        return "logs"
    return "unknown"


def detect_file_type(filename: str) -> str:
    """Type de fichier normalisé (pdf / md / txt / log / other) depuis l'extension."""
    ext = Path(filename).suffix.lower().lstrip(".")
    return ext if ext in {"pdf", "md", "txt", "log"} else "other"


@dataclass
class LoadedPage:
    """Un morceau de texte brut associé à ses métadonnées de source."""

    text: str
    filename: str
    page: int
    source_path: str
    db_type: str = "unknown"
    file_type: str = "other"


def _read_text_file(path: Path) -> str:
    """Lit un fichier texte en tolérant les encodages non-UTF8."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")


def _load_pdf(path: Path, data_root: Path) -> List[LoadedPage]:
    from pypdf import PdfReader

    pages: List[LoadedPage] = []
    rel = str(path.relative_to(data_root))
    db_type = detect_db_type(rel)
    file_type = detect_file_type(path.name)

    # L'ouverture, le déchiffrement et le comptage des pages sont "paresseux"
    # chez pypdf : on englobe tout dans un try pour qu'un PDF chiffré ou corrompu
    # n'interrompe pas l'ingestion complète.
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # PDF chiffré avec mot de passe vide (fréquent)
            except Exception:
                pass
        num_pages = len(reader.pages)
    except Exception as exc:
        logger.warning("PDF illisible, ignoré : %s (%s)", path.name, exc)
        return pages

    for i in range(num_pages):
        try:
            text = reader.pages[i].extract_text() or ""
        except Exception as exc:
            logger.warning("Extraction échouée %s page %s : %s", path.name, i + 1, exc)
            continue
        if text.strip():
            pages.append(
                LoadedPage(
                    text=text,
                    filename=path.name,
                    page=i + 1,
                    source_path=rel,
                    db_type=db_type,
                    file_type=file_type,
                )
            )
    return pages


def _load_text(path: Path, data_root: Path) -> List[LoadedPage]:
    text = _read_text_file(path)
    if not text.strip():
        return []
    rel = str(path.relative_to(data_root))
    return [
        LoadedPage(
            text=text, filename=path.name, page=1, source_path=rel,
            db_type=detect_db_type(rel), file_type=detect_file_type(path.name),
        )
    ]


def list_source_files(data_path: str) -> List[Path]:
    """Liste (triée) tous les fichiers supportés sous data/, sans les parser."""
    data_root = Path(data_path).resolve()
    if not data_root.exists():
        return []
    return sorted(
        p
        for p in data_root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def count_files_by_db_type(data_path: str) -> dict:
    """Compte les fichiers présents sur disque par db_type (diagnostic ingestion)."""
    data_root = Path(data_path).resolve()
    counts = {"oracle": 0, "postgresql": 0, "logs": 0, "unknown": 0, "total": 0}
    for path in list_source_files(data_path):
        rel = str(path.relative_to(data_root))
        counts[detect_db_type(rel)] += 1
        counts["total"] += 1
    return counts


def load_documents(data_path: str) -> List[LoadedPage]:
    """Parcourt récursivement data/ et retourne toutes les pages extraites."""
    data_root = Path(data_path).resolve()
    if not data_root.exists():
        logger.warning("Dossier de données introuvable : %s", data_root)
        return []

    pages: List[LoadedPage] = []
    files = sorted(
        p
        for p in data_root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )

    for path in files:
        ext = path.suffix.lower()
        if ext in PDF_EXTENSIONS:
            loaded = _load_pdf(path, data_root)
        else:
            loaded = _load_text(path, data_root)
        logger.info("Chargé %-40s -> %d page(s)", path.name, len(loaded))
        pages.extend(loaded)

    logger.info("Total : %d fichier(s), %d page(s) de texte.", len(files), len(pages))
    return pages
