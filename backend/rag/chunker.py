"""Découpage récursif du texte en chunks, préservant titres / sections / listes.

Remplace l'ancienne fenêtre glissante « plate » par un splitter récursif de type
RecursiveCharacterTextSplitter : on essaie de couper d'abord sur les frontières
sémantiques fortes (double saut de ligne = paragraphe), puis de plus en plus fines
(ligne, phrase, mot). On préserve ainsi les titres, sections et listes.

Chaque chunk porte des métadonnées riches :
    filename, page, title, section, chunk_id, source_path
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from rag.loader import LoadedPage

# Séparateurs hiérarchiques (du plus « fort » au plus « fin »).
_SEPARATORS = ["\n\n", "\n", ". ", "; ", ", ", " ", ""]

# En-tête Markdown : "# Titre", "## Sous-titre", ...
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# Ligne de type titre dans un PDF : courte, majoritairement en MAJUSCULES,
# ou numérotée façon manuel Oracle ("3.2 Managing Tablespaces").
_PDF_HEADING_RE = re.compile(r"^(?:\d+(?:\.\d+)*\s+)?[A-Z][A-Za-z0-9 ,/&()\-]{2,70}$")


@dataclass
class Chunk:
    """Un chunk indexable avec un identifiant unique et ses métadonnées."""

    id: str
    text: str
    filename: str
    page: int
    chunk_id: int
    source_path: str
    title: str = ""
    section: str = ""
    db_type: str = "unknown"
    file_type: str = "other"


def _looks_like_heading(line: str) -> bool:
    """Heuristique : la ligne ressemble-t-elle à un titre (PDF non-markdown) ?"""
    s = line.strip()
    if not (3 <= len(s) <= 72):
        return False
    if s.endswith((".", ":", ";", ",")):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
    if upper_ratio >= 0.7:  # ligne majoritairement en capitales
        return True
    return bool(_PDF_HEADING_RE.match(s))


def _detect_title(text: str) -> str:
    """Extrait un titre représentatif du passage (1re ligne markdown/majuscule)."""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _MD_HEADING_RE.match(line)
        if m:
            return m.group(2).strip()
        if _looks_like_heading(line):
            return line
        break  # 1re ligne non vide non-titre → pas de titre en tête
    return ""


def _recursive_split(text: str, chunk_size: int, seps: List[str]) -> List[str]:
    """Découpe récursive en respectant la hiérarchie des séparateurs."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    sep = seps[0] if seps else ""
    rest = seps[1:] if len(seps) > 1 else [""]

    if sep == "":
        # Dernier recours : coupe dure par tranches de chunk_size.
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    parts = text.split(sep)
    pieces: List[str] = []
    buf = ""
    for part in parts:
        candidate = part if not buf else buf + sep + part
        if len(candidate) <= chunk_size:
            buf = candidate
            continue
        if buf:
            pieces.append(buf)
        if len(part) > chunk_size:
            # Le fragment seul dépasse : on descend d'un niveau de séparateur.
            pieces.extend(_recursive_split(part, chunk_size, rest))
            buf = ""
        else:
            buf = part
    if buf:
        pieces.append(buf)
    return [p for p in pieces if p.strip()]


def _merge_with_overlap(
    pieces: List[str], chunk_size: int, overlap: int
) -> List[str]:
    """Regroupe les fragments jusqu'à chunk_size, avec chevauchement (overlap)."""
    if not pieces:
        return []
    chunks: List[str] = []
    current = ""
    for piece in pieces:
        candidate = piece if not current else current + "\n" + piece
        if len(candidate) <= chunk_size or not current:
            current = candidate
        else:
            chunks.append(current.strip())
            # Amorce le chunk suivant avec la queue du précédent (overlap).
            tail = current[-overlap:] if overlap > 0 else ""
            current = (tail + "\n" + piece).strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Découpe récursive d'un texte (compatible avec l'ancienne signature)."""
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    if overlap >= chunk_size:
        overlap = chunk_size // 4
    pieces = _recursive_split(text, chunk_size, _SEPARATORS)
    return _merge_with_overlap(pieces, chunk_size, overlap)


def _split_markdown_sections(text: str):
    """Découpe un markdown en (section_title, corps) sur les en-têtes.

    Préserve les titres/sections : chaque bloc garde le titre courant en contexte.
    """
    sections = []
    current_title = ""
    buf: List[str] = []
    for line in text.splitlines():
        m = _MD_HEADING_RE.match(line)
        if m:
            if buf:
                sections.append((current_title, "\n".join(buf)))
                buf = []
            current_title = m.group(2).strip()
            buf.append(line)  # on garde l'en-tête dans le corps du chunk
        else:
            buf.append(line)
    if buf:
        sections.append((current_title, "\n".join(buf)))
    return sections or [("", text)]


def chunk_pages(
    pages: List[LoadedPage], chunk_size: int, overlap: int
) -> List[Chunk]:
    """Transforme les pages chargées en chunks enrichis, prêts à indexer."""
    chunks: List[Chunk] = []
    for page in pages:
        is_markdown = page.filename.lower().endswith(".md")
        if is_markdown:
            blocks = _split_markdown_sections(page.text)
        else:
            blocks = [("", page.text)]

        idx = 0
        for section_title, body in blocks:
            for piece in chunk_text(body, chunk_size, overlap):
                title = _detect_title(piece) or section_title
                uid = f"{page.source_path}::p{page.page}::c{idx}"
                chunks.append(
                    Chunk(
                        id=uid,
                        text=piece,
                        filename=page.filename,
                        page=page.page,
                        chunk_id=idx,
                        source_path=page.source_path,
                        title=title,
                        section=section_title,
                        db_type=page.db_type,
                        file_type=page.file_type,
                    )
                )
                idx += 1
    return chunks
