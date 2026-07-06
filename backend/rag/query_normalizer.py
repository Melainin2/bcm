"""Normalisation de la requête : correction de fautes + acronymes DBA.

Deux niveaux :
  - Correction CERTAINE (table explicite + fuzzy à haut score) → appliquée au
    retrieval, affichée discrètement « Question corrigée : … ».
  - Suggestion en cas de DOUTE (acronyme proche) → « Did you mean AWR ? ».

L'expansion des acronymes (AWR → Automatic Workload Repository) enrichit la requête
de retrieval sans changer la question affichée.

rapidfuzz fournit le fuzzy matching (rapide, C++).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from rapidfuzz import fuzz, process

import config

# --- Dictionnaire d'acronymes DBA (sigle -> forme longue) --------------------
ORACLE_ACRONYMS: Dict[str, str] = {
    "AWR": "Automatic Workload Repository",
    "ASH": "Active Session History",
    "ADDM": "Automatic Database Diagnostic Monitor",
    "RMAN": "Recovery Manager",
    "ASM": "Automatic Storage Management",
    "RAC": "Real Application Clusters",
    "SGA": "System Global Area",
    "PGA": "Program Global Area",
    "CDB": "Container Database",
    "PDB": "Pluggable Database",
    "UNDO": "undo tablespace",
    "REDO": "redo log",
    "SCN": "System Change Number",
    "TDE": "Transparent Data Encryption",
    "DG": "Data Guard",
    "MAA": "Maximum Availability Architecture",
    "OEM": "Oracle Enterprise Manager",
    "TNS": "Transparent Network Substrate",
}
POSTGRES_ACRONYMS: Dict[str, str] = {
    "WAL": "Write-Ahead Log",
    "VACUUM": "VACUUM dead tuple cleanup",
    "AUTOVACUUM": "autovacuum",
    "MVCC": "Multiversion Concurrency Control",
    "EXPLAIN": "EXPLAIN query plan",
    "ANALYZE": "ANALYZE statistics",
    "INDEX": "index",
    "DEADLOCK": "deadlock",
    "TOAST": "The Oversized-Attribute Storage Technique",
    "PITR": "Point-In-Time Recovery",
    "CTE": "Common Table Expression",
    "FDW": "Foreign Data Wrapper",
}
ACRONYMS: Dict[str, str] = {**ORACLE_ACRONYMS, **POSTGRES_ACRONYMS}

# --- Corrections CERTAINES (fautes fréquentes, haute précision) ---------------
COMMON_TYPOS: Dict[str, str] = {
    "wals": "WAL",
    "vacume": "VACUUM",
    "vaccum": "VACUUM",
    "vacum": "VACUUM",
    "orcale": "Oracle",
    "oracel": "Oracle",
    "postgressql": "PostgreSQL",
    "postgrsql": "PostgreSQL",
    "posgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "tablspace": "tablespace",
    "tablescape": "tablespace",
    "performence": "performance",
    "performace": "performance",
    "monitore": "monitor",
    "databse": "database",
    "recvery": "recovery",
    "bakup": "backup",
    "indexs": "indexes",
}

# --- Vocabulaire pour le fuzzy matching (corrections certaines par proximité) --
DOMAIN_VOCAB: List[str] = [
    "postgresql", "oracle", "database", "tablespace", "vacuum", "autovacuum",
    "index", "partition", "replication", "recovery", "backup", "performance",
    "checkpoint", "transaction", "rollback", "commit", "sequence", "trigger",
    "schema", "cluster", "instance", "listener", "redo", "undo", "archive",
    "datafile", "controlfile", "segment", "buffer", "deadlock", "analyze",
    "explain", "optimizer", "statistics", "connection", "session", "monitor",
    "concurrency", "isolation", "constraint", "materialized", "wraparound",
]

_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_MIN_FUZZY_LEN = 5


@dataclass
class QueryNormalization:
    original: str
    corrected: str                      # requête après corrections certaines
    expanded: str                       # corrected + expansions d'acronymes (retrieval)
    corrections: List[Tuple[str, str]] = field(default_factory=list)  # (avant, après)
    suggestions: List[Tuple[str, str]] = field(default_factory=list)  # did-you-mean
    acronyms: List[Tuple[str, str]] = field(default_factory=list)     # (sigle, forme)

    @property
    def corrected_query(self) -> str:
        """La requête corrigée à afficher, ou None si rien n'a changé."""
        return self.corrected if self.corrections else None

    def as_dict(self) -> dict:
        return {
            "corrections": [{"from": a, "to": b} for a, b in self.corrections],
            "suggestions": [{"from": a, "to": b} for a, b in self.suggestions],
            "acronyms": [{"acronym": a, "expansion": b} for a, b in self.acronyms],
        }


def _correct_token(token: str) -> Tuple[str, bool]:
    """Corrige un mot (certain). Retourne (mot, a_été_corrigé)."""
    low = token.lower()
    if low in COMMON_TYPOS:
        return COMMON_TYPOS[low], True
    if low in DOMAIN_VOCAB or len(low) < _MIN_FUZZY_LEN:
        return token, False
    match = process.extractOne(low, DOMAIN_VOCAB, scorer=fuzz.ratio)
    if match and match[1] >= config.FUZZY_THRESHOLD and match[0] != low:
        return match[0], True
    return token, False


def _acronym_suggestion(token: str):
    """Token inconnu proche d'un acronyme (ARW→AWR) → suggestion (doute)."""
    up = token.upper()
    if up in ACRONYMS or not (3 <= len(up) <= 6):
        return None
    up_sorted = "".join(sorted(up))
    for acro in ACRONYMS:
        if len(acro) == len(up) and "".join(sorted(acro)) == up_sorted and acro != up:
            return acro  # transposition (ARW↔AWR) : forte présomption
    match = process.extractOne(up, list(ACRONYMS.keys()), scorer=fuzz.ratio)
    if match and match[1] >= 78 and match[0] != up:
        return match[0]
    return None


def normalize_query(question: str) -> QueryNormalization:
    """Analyse et normalise la question : corrections, suggestions, expansions."""
    if not config.QUERY_PREPROCESS:
        return QueryNormalization(question, question, question)

    corrections: List[Tuple[str, str]] = []
    suggestions: List[Tuple[str, str]] = []
    acronyms: List[Tuple[str, str]] = []

    def _replace(m: "re.Match") -> str:
        token = m.group(0)
        fixed, changed = _correct_token(token)
        if changed:
            corrections.append((token, fixed))
            return fixed
        sugg = _acronym_suggestion(token)
        if sugg:
            suggestions.append((token, sugg))
        return token

    corrected = _WORD_RE.sub(_replace, question)

    expanded = corrected
    for sigle, forme in ACRONYMS.items():
        if re.search(rf"\b{re.escape(sigle)}\b", corrected, re.IGNORECASE):
            acronyms.append((sigle, forme))
            expanded = f"{expanded} {forme}"

    return QueryNormalization(
        original=question,
        corrected=corrected.strip(),
        expanded=expanded.strip(),
        corrections=corrections,
        suggestions=suggestions,
        acronyms=acronyms,
    )
