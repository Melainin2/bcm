"""Jeux de questions d'évaluation DBA (Oracle + PostgreSQL) avec vérité terrain.

Chaque item :
    question       : la question posée (EN / FR / AR)
    expected_files : fichier(s) source attendu(s) (vérité terrain, granularité fichier)
    lang           : langue attendue de la réponse
    answerable     : True si la documentation contient la réponse

Les questions OUT_OF_DOMAIN servent à mesurer le taux d'hallucination : le système
DOIT s'abstenir (message de repli + confidence LOW) plutôt que d'inventer.

Le corpus réel : docs Oracle riches (PDF) + 2 fiches PostgreSQL (vacuum, performance)
+ 2 fiches Oracle (tablespaces, ora-01555) + 1 log. Les fichiers attendus reflètent
ce corpus. Le jeu est volontairement extensible (voir generate_questions()).
"""

from __future__ import annotations

from typing import Dict, List

ORA_ADMIN = "database-administrators-guide.pdf"
ORA_BACKUP = "database-backup-and-recovery-reference.pdf"
ORA_PERF = "database-performance-tuning-guide.pdf"
ORA_HA = "high-availability-overview-and-best-practices.pdf"
ORA_ARCH = "db-19c-architecture.pdf"
ORA_DIAG = "diag-pack-ow09-133950.pdf"
ORA_TBS = "oracle_tablespaces.md"
ORA_UNDO = "oracle_undo_ora01555.md"
PG_VACUUM = "postgresql_vacuum.md"
PG_PERF = "postgresql_performance.md"

# Toute source Oracle acceptable (pour des questions génériques Oracle).
ORA_ANY = [ORA_ADMIN, ORA_ARCH, ORA_TBS, ORA_UNDO, ORA_BACKUP, ORA_PERF, ORA_HA, ORA_DIAG]


ORACLE_QUESTIONS: List[Dict] = [
    {"question": "What is an Oracle tablespace?", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "en"},
    {"question": "How do I create a tablespace in Oracle?", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "en"},
    {"question": "What is the difference between a permanent and a temporary tablespace?", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "en"},
    {"question": "What causes the ORA-01555 snapshot too old error?", "expected_files": [ORA_UNDO], "lang": "en"},
    {"question": "How can I prevent ORA-01555 errors?", "expected_files": [ORA_UNDO], "lang": "en"},
    {"question": "What is the undo tablespace used for in Oracle?", "expected_files": [ORA_UNDO, ORA_ADMIN, ORA_TBS], "lang": "en"},
    {"question": "How does Oracle Recovery Manager RMAN perform backups?", "expected_files": [ORA_BACKUP], "lang": "en"},
    {"question": "What is a whole database backup in RMAN?", "expected_files": [ORA_BACKUP], "lang": "en"},
    {"question": "How do I restore and recover a database with RMAN?", "expected_files": [ORA_BACKUP], "lang": "en"},
    {"question": "What is point-in-time recovery in Oracle?", "expected_files": [ORA_BACKUP], "lang": "en"},
    {"question": "How do I tune SQL query performance in Oracle?", "expected_files": [ORA_PERF], "lang": "en"},
    {"question": "What is the Automatic Workload Repository AWR?", "expected_files": [ORA_DIAG, ORA_PERF], "lang": "en"},
    {"question": "How does the Oracle optimizer use statistics?", "expected_files": [ORA_PERF, ORA_ADMIN], "lang": "en"},
    {"question": "What is the System Global Area SGA in Oracle?", "expected_files": [ORA_ARCH, ORA_ADMIN, ORA_PERF], "lang": "en"},
    {"question": "What is the difference between the SGA and the PGA?", "expected_files": [ORA_ARCH, ORA_ADMIN, ORA_PERF], "lang": "en"},
    {"question": "What are redo log files in Oracle?", "expected_files": [ORA_ADMIN, ORA_ARCH], "lang": "en"},
    {"question": "What is Oracle Data Guard used for?", "expected_files": [ORA_HA], "lang": "en"},
    {"question": "What is Oracle Real Application Clusters RAC?", "expected_files": [ORA_HA, ORA_ARCH], "lang": "en"},
    {"question": "What is the Maximum Availability Architecture MAA?", "expected_files": [ORA_HA], "lang": "en"},
    {"question": "What is a pluggable database PDB in a container database CDB?", "expected_files": [ORA_ARCH, ORA_ADMIN], "lang": "en"},
    {"question": "How do I add a datafile to a tablespace?", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "en"},
    {"question": "What is Automatic Storage Management ASM?", "expected_files": [ORA_ADMIN, ORA_ARCH], "lang": "en"},
    {"question": "How do I manage undo retention in Oracle?", "expected_files": [ORA_UNDO, ORA_ADMIN], "lang": "en"},
    {"question": "What is a control file in an Oracle database?", "expected_files": [ORA_ADMIN, ORA_ARCH, ORA_BACKUP], "lang": "en"},
    {"question": "How does archived redo log mode work?", "expected_files": [ORA_ADMIN, ORA_BACKUP], "lang": "en"},
    # Français
    {"question": "Qu'est-ce qu'un tablespace Oracle ?", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "fr"},
    {"question": "Quelle est la cause de l'erreur ORA-01555 ?", "expected_files": [ORA_UNDO], "lang": "fr"},
    {"question": "Comment fonctionne la sauvegarde RMAN ?", "expected_files": [ORA_BACKUP], "lang": "fr"},
    {"question": "Qu'est-ce que la SGA dans Oracle ?", "expected_files": [ORA_ARCH, ORA_ADMIN, ORA_PERF], "lang": "fr"},
    {"question": "À quoi sert Oracle Data Guard ?", "expected_files": [ORA_HA], "lang": "fr"},
    # Arabe
    {"question": "ما هو الـ tablespace في Oracle؟", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "ar"},
    {"question": "ما سبب الخطأ ORA-01555؟", "expected_files": [ORA_UNDO], "lang": "ar"},
    {"question": "كيف تعمل النسخ الاحتياطي باستخدام RMAN؟", "expected_files": [ORA_BACKUP], "lang": "ar"},
    # Robustesse (fautes de frappe / acronymes)
    {"question": "What is an orcale tablspace?", "expected_files": [ORA_TBS, ORA_ADMIN], "lang": "en"},
    {"question": "Explain the ARW report in Oracle", "expected_files": [ORA_DIAG, ORA_PERF], "lang": "en"},
]

POSTGRES_QUESTIONS: List[Dict] = [
    {"question": "How does VACUUM work in PostgreSQL?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "What is the difference between VACUUM and VACUUM FULL?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "What is autovacuum in PostgreSQL?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "How does VACUUM reclaim space from dead tuples?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "What is MVCC in PostgreSQL and why does it create dead tuples?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "How do I prevent transaction ID wraparound in PostgreSQL?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "When should I run VACUUM ANALYZE?", "expected_files": [PG_VACUUM, PG_PERF], "lang": "en"},
    {"question": "What causes table bloat in PostgreSQL?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "How can I improve PostgreSQL performance?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "How do indexes improve query performance in PostgreSQL?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "What does EXPLAIN ANALYZE show in PostgreSQL?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "How should I configure shared_buffers in PostgreSQL?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "How does the PostgreSQL query planner choose a plan?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "What are the main parameters to tune for PostgreSQL performance?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "How do I speed up slow queries in PostgreSQL?", "expected_files": [PG_PERF], "lang": "en"},
    {"question": "What is the role of work_mem in PostgreSQL performance?", "expected_files": [PG_PERF], "lang": "en"},
    # Français
    {"question": "Comment fonctionne le VACUUM dans PostgreSQL ?", "expected_files": [PG_VACUUM], "lang": "fr"},
    {"question": "Qu'est-ce que l'autovacuum ?", "expected_files": [PG_VACUUM], "lang": "fr"},
    {"question": "Comment améliorer les performances de PostgreSQL ?", "expected_files": [PG_PERF], "lang": "fr"},
    {"question": "Comment récupérer l'espace des lignes mortes en PostgreSQL ?", "expected_files": [PG_VACUUM], "lang": "fr"},
    # Arabe
    {"question": "كيف يعمل VACUUM في PostgreSQL؟", "expected_files": [PG_VACUUM], "lang": "ar"},
    {"question": "كيف أحسّن أداء PostgreSQL؟", "expected_files": [PG_PERF], "lang": "ar"},
    # Robustesse
    {"question": "how does postgressql vaccum work?", "expected_files": [PG_VACUUM], "lang": "en"},
    {"question": "improve postgrsql performace", "expected_files": [PG_PERF], "lang": "en"},
]

# Questions HORS domaine : le système doit S'ABSTENIR (anti-hallucination).
OUT_OF_DOMAIN: List[Dict] = [
    {"question": "What is the capital of France?", "expected_files": [], "lang": "en", "answerable": False},
    {"question": "How do I bake a chocolate cake?", "expected_files": [], "lang": "en", "answerable": False},
    {"question": "Who won the 2018 FIFA World Cup?", "expected_files": [], "lang": "en", "answerable": False},
    {"question": "How do I configure a MongoDB sharded cluster?", "expected_files": [], "lang": "en", "answerable": False},
    {"question": "Quelle est la météo à Paris demain ?", "expected_files": [], "lang": "fr", "answerable": False},
    {"question": "How do I set up Kubernetes autoscaling?", "expected_files": [], "lang": "en", "answerable": False},
]


def _finalize(items: List[Dict], default_answerable: bool = True) -> List[Dict]:
    out = []
    for it in items:
        d = dict(it)
        d.setdefault("answerable", default_answerable)
        out.append(d)
    return out


def all_questions() -> List[Dict]:
    """Ensemble complet (answerable + out-of-domain)."""
    return (
        _finalize(ORACLE_QUESTIONS)
        + _finalize(POSTGRES_QUESTIONS)
        + _finalize(OUT_OF_DOMAIN, default_answerable=False)
    )


# Alias utilisé par le banc d'essai d'embeddings (rétrocompat).
EVAL_QUESTIONS = _finalize(ORACLE_QUESTIONS) + _finalize(POSTGRES_QUESTIONS)
