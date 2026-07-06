"""API FastAPI de DBA-GPT (production)."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Optional

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
from rag.vectorstore import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dba-gpt")

# État partagé, initialisé au démarrage.
_state = {"pipeline": None, "store": None, "error": None}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Charge ChromaDB au démarrage ; le pipeline Claude est chargé à la demande."""
    try:
        _state["store"] = VectorStore()
        logger.info("ChromaDB chargé : %d chunks indexés.", _state["store"].count())
    except Exception as exc:  # pragma: no cover
        logger.exception("Échec du chargement de ChromaDB : %s", exc)
        _state["error"] = str(exc)
    yield


app = FastAPI(title="DBA-GPT", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Modèles Pydantic --------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = Field(None, ge=1, le=20)
    # Modèle Claude choisi dans l'interface. Si absent -> CLAUDE_MODEL par défaut.
    model: Optional[str] = Field(None)


class SourceModel(BaseModel):
    id: str
    filename: Optional[str] = None
    page: Optional[int] = None
    section: Optional[str] = ""
    similarity: Optional[float] = None
    rerank_score: Optional[float] = None
    excerpt: str = ""
    source_url: Optional[str] = None
    source_path: Optional[str] = None


class ConfidenceModel(BaseModel):
    level: str = "LOW"
    score: float = 0.0


class ChatResponse(BaseModel):
    answer: str
    language: str = "en"
    confidence: ConfidenceModel = Field(default_factory=ConfidenceModel)
    corrected_query: Optional[str] = None
    sources: List[SourceModel] = Field(default_factory=list)
    timing: Dict[str, float] = Field(default_factory=dict)
    query_analysis: Dict = Field(default_factory=dict)
    model: str = ""


def _get_pipeline():
    """Instancie le pipeline RAG (et le client Claude) au premier appel."""
    if _state["pipeline"] is None:
        from rag.pipeline import RAGPipeline

        _state["pipeline"] = RAGPipeline()
    return _state["pipeline"]


# --- Endpoints ---------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    """État de santé du service. N'expose JAMAIS la clé API (booléen uniquement)."""
    store = _state["store"]
    chroma_ready = store is not None
    documents_indexed = store.count() if chroma_ready else 0
    rag_ready = chroma_ready and documents_indexed > 0
    return {
        "status": "ok" if rag_ready else "degraded",
        "rag_ready": rag_ready,
        "chroma_ready": chroma_ready,
        "documents_indexed": documents_indexed,
        "claude_model": config.CLAUDE_MODEL,
        "available_claude_models": config.AVAILABLE_CLAUDE_MODELS,
        # Alias rétrocompatible (ancien frontend/tests).
        "model": config.CLAUDE_MODEL,
        "embedding_model": config.EMBEDDING_MODEL,
        "reranker_model": config.RERANKER_MODEL if config.USE_RERANKER else None,
        "similarity_threshold": config.SIMILARITY_THRESHOLD,
        "high_confidence_threshold": config.HIGH_CONFIDENCE_THRESHOLD,
        "medium_confidence_threshold": config.MEDIUM_CONFIDENCE_THRESHOLD,
        "retriever_top_k": config.RETRIEVER_TOP_K,
        "rerank_top_k": config.RERANK_TOP_K,
        # Sécurité : booléen seulement, jamais la valeur de la clé.
        "api_key_configured": bool(config.ANTHROPIC_API_KEY),
        "error": _state["error"],
    }


@app.get("/api/stats")
def stats() -> dict:
    """Statistiques réelles du système RAG (documents, chunks, config, modèles)."""
    from rag.stats import build_stats

    data = build_stats(_state["store"])
    data["error"] = _state["error"]
    return data


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    store = _state["store"]
    if store is None:
        raise HTTPException(status_code=503, detail="Base vectorielle indisponible.")
    if store.count() == 0:
        raise HTTPException(
            status_code=400,
            detail="Aucun document indexé. Lancez `python scripts/ingest.py`.",
        )
    # Validation du modèle Claude demandé : doit faire partie des modèles autorisés.
    model = (req.model or "").strip() or None
    if model is not None and model not in config.AVAILABLE_CLAUDE_MODELS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "model_not_allowed",
                "message": (
                    f"Modèle Claude non autorisé : {model}. "
                    f"Modèles disponibles : {', '.join(config.AVAILABLE_CLAUDE_MODELS)}."
                ),
            },
        )

    try:
        pipeline = _get_pipeline()
    except RuntimeError as exc:
        # Clé API manquante.
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        result = pipeline.answer(req.question, req.top_k, model)
    except anthropic.NotFoundError:
        # Le modèle n'existe pas / n'est pas activé pour ce compte Anthropic.
        raise HTTPException(
            status_code=400,
            detail={
                "code": "model_unavailable",
                "message": (
                    "Ce modèle Claude n'est pas disponible pour votre compte. "
                    "Choisissez un autre modèle."
                ),
            },
        )
    except anthropic.APIStatusError as exc:
        if getattr(exc, "status_code", None) == 404:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "model_unavailable",
                    "message": (
                        "Ce modèle Claude n'est pas disponible pour votre compte. "
                        "Choisissez un autre modèle."
                    ),
                },
            )
        # Autre erreur API : on logue le détail côté serveur, message générique côté client.
        logger.exception("Erreur API Claude : %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "claude_error",
                "message": "Erreur lors de la génération. Réessayez plus tard.",
            },
        )
    except Exception as exc:
        # Jamais l'exception brute au client (peut contenir du JSON Anthropic).
        logger.exception("Erreur lors de la génération : %s", exc)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "claude_error",
                "message": "Erreur lors de la génération. Réessayez plus tard.",
            },
        )

    return ChatResponse(**result)


@app.get("/api/source/{source_id:path}")
def get_source(source_id: str) -> dict:
    store = _state["store"]
    if store is None:
        raise HTTPException(status_code=503, detail="Base vectorielle indisponible.")
    source = store.get_by_id(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source introuvable.")
    return source


@app.get("/api/file/{source_path:path}")
def get_file(source_path: str):
    """Sert le fichier source original (ex. PDF) pour ouverture à la bonne page.

    Sécurité : on résout le chemin et on vérifie qu'il reste bien SOUS data/,
    pour empêcher toute traversée de répertoire (../).
    """
    data_root = Path(config.DATA_PATH).resolve()
    target = (data_root / source_path).resolve()
    if not str(target).startswith(str(data_root)) or not target.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    media = "application/pdf" if target.suffix.lower() == ".pdf" else None
    return FileResponse(str(target), media_type=media, filename=target.name)


# --- Frontend statique (déploiement Render en service unique) ----------------
# Le backend sert le build React (frontend/dist) sur le même domaine, avec un
# fallback SPA vers index.html. Les routes /api/* ci-dessus ont la priorité car
# elles sont déclarées AVANT ce montage. Si le build n'existe pas (dev local
# sans build, tests), on n'ajoute rien : les endpoints API restent disponibles.
_FRONTEND_DIST = Path(
    os.getenv(
        "FRONTEND_DIST",
        str(Path(__file__).resolve().parent.parent / "frontend" / "dist"),
    )
).resolve()


def _mount_frontend() -> None:
    if not _FRONTEND_DIST.is_dir() or not (_FRONTEND_DIST / "index.html").is_file():
        logger.warning(
            "Build frontend introuvable (%s) : l'UI ne sera pas servie. "
            "Lancez `cd frontend && npm run build`.",
            _FRONTEND_DIST,
        )
        return

    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        # Une requête /api/* non résolue ne doit pas renvoyer l'index HTML.
        if full_path.startswith("api/") or full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        # Fichier statique réel (favicon, vite.svg, etc.) : le servir directement.
        if full_path:
            candidate = (_FRONTEND_DIST / full_path).resolve()
            if str(candidate).startswith(str(_FRONTEND_DIST)) and candidate.is_file():
                return FileResponse(str(candidate))
        # Sinon : fallback SPA (React Router) vers index.html.
        return FileResponse(str(_FRONTEND_DIST / "index.html"))

    logger.info("Frontend servi depuis %s", _FRONTEND_DIST)


_mount_frontend()
