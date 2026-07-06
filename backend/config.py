"""Configuration centrale de DBA-GPT (lue depuis les variables d'environnement)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Charge le fichier backend/.env s'il existe.
load_dotenv(BASE_DIR / ".env")


def _resolve(path: str) -> str:
    """Résout un chemin relatif par rapport au dossier backend/."""
    p = Path(path)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    return str(p)


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Claude / Anthropic ------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
# claude-3-5-sonnet-latest a été retiré : on utilise le modèle Sonnet actuel.
# Vous pouvez mettre claude-opus-4-8 pour une qualité maximale.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6").strip()
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))


def _model_list(raw: str) -> list[str]:
    """Parse une liste de modèles séparés par des virgules, en dédupliquant."""
    seen: list[str] = []
    for m in raw.split(","):
        m = m.strip()
        if m and m not in seen:
            seen.append(m)
    return seen


# Modèles Claude sélectionnables depuis l'interface. Le modèle par défaut
# (CLAUDE_MODEL) est toujours inclus, même s'il est absent de la liste .env.
AVAILABLE_CLAUDE_MODELS = _model_list(
    os.getenv(
        "AVAILABLE_CLAUDE_MODELS",
        "claude-sonnet-4-6,claude-sonnet-5",
    )
)
if CLAUDE_MODEL and CLAUDE_MODEL not in AVAILABLE_CLAUDE_MODELS:
    AVAILABLE_CLAUDE_MODELS.insert(0, CLAUDE_MODEL)

# --- RAG : chemins & collection ---------------------------------------------
CHROMA_PATH = _resolve(os.getenv("CHROMA_PATH", "../chroma_db"))
DATA_PATH = _resolve(os.getenv("DATA_PATH", "../data"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "dba_docs")

# --- Embeddings --------------------------------------------------------------
# Défaut MULTILINGUE (AR/FR/EN) : intfloat/multilingual-e5-base.
# embeddings.py applique automatiquement les préfixes E5 (« query: » / « passage: »)
# ou l'instruction BGE selon le nom du modèle. Alternatives : intfloat/
# multilingual-e5-large (qualité max), BAAI/bge-small-en-v1.5 (EN, léger, hors-ligne).
# Comparez avec scripts/benchmark_embeddings.py. Reconstruire ChromaDB après changement.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")

# --- Retrieval / reranking (entonnoir) ---------------------------------------
# Pipeline : ChromaDB top RETRIEVER_TOP_K → filtre similarité ≥ SIMILARITY_THRESHOLD
#            → reranker → RERANK_TOP_K → Claude.
RETRIEVER_TOP_K = int(os.getenv("RETRIEVER_TOP_K", os.getenv("RETRIEVE_K", "20")))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", os.getenv("TOP_K", "5")))
# Alias rétrocompatibles.
RETRIEVE_K = RETRIEVER_TOP_K
TOP_K = RERANK_TOP_K
USE_RERANKER = _flag("USE_RERANKER", _flag("RERANK_ENABLED", True))
RERANK_ENABLED = USE_RERANKER  # alias
# Défaut MULTILINGUE : BAAI/bge-reranker-base. Alternative EN légère :
# cross-encoder/ms-marco-MiniLM-L-6-v2 (~90 Mo).
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-base")

# --- Seuils de similarité & de confiance -------------------------------------
# Filtre de pertinence : tout chunk dont la similarité dense < ce seuil est écarté.
# Si aucun chunk ne passe → Claude N'EST PAS appelé, sources = [], confidence = LOW.
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.70"))
# Niveau de confiance (sur le score de pertinence du meilleur passage) :
#   score >= HIGH_CONFIDENCE_THRESHOLD              -> HIGH
#   MEDIUM_CONFIDENCE_THRESHOLD..HIGH               -> MEDIUM
#   score <  MEDIUM_CONFIDENCE_THRESHOLD            -> LOW (pas d'appel Claude)
HIGH_CONFIDENCE_THRESHOLD = float(os.getenv("HIGH_CONFIDENCE_THRESHOLD", "0.85"))
MEDIUM_CONFIDENCE_THRESHOLD = float(os.getenv("MEDIUM_CONFIDENCE_THRESHOLD", "0.70"))
# Aliases rétrocompatibles.
CONFIDENCE_HIGH = HIGH_CONFIDENCE_THRESHOLD

# --- Chunking ----------------------------------------------------------------
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# --- Préprocessing requête ---------------------------------------------------
QUERY_PREPROCESS = _flag("QUERY_PREPROCESS", True)  # acronymes + fautes de frappe
FUZZY_THRESHOLD = int(os.getenv("FUZZY_THRESHOLD", "82"))  # score rapidfuzz 0-100

# --- API ---------------------------------------------------------------------
# Origines autorisées pour le frontend (séparées par des virgules).
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
