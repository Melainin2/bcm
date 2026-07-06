"""Banc d'essai des modèles d'embedding : choisit le meilleur par retrieval.

Compare plusieurs modèles sur un jeu de questions étiquetées (fichier source
attendu) et mesure Recall@k / MRR. Le modèle gagnant peut être placé dans
`.env` (EMBEDDING_MODEL).

Usage :
    cd backend
    python scripts/benchmark_embeddings.py                 # tous les modèles
    python scripts/benchmark_embeddings.py --models e5-base bge-small
    python scripts/benchmark_embeddings.py --k 5

⚠️  Chaque modèle ré-encode l'intégralité du corpus dans une collection temporaire
    en mémoire. e5-large est volumineux (~2 Go) : lancez-le seul si la bande
    passante est limitée.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from rag.chunker import chunk_pages  # noqa: E402
from rag.loader import load_documents  # noqa: E402

MODELS = {
    "bge-small": "BAAI/bge-small-en-v1.5",
    "bge-base": "BAAI/bge-base-en-v1.5",
    "e5-base": "intfloat/multilingual-e5-base",
    "e5-large": "intfloat/multilingual-e5-large",
}

# Jeu d'évaluation partagé avec evaluation/ (fichier source attendu par question).
try:
    from evaluation.questions import EVAL_QUESTIONS  # type: ignore
except Exception:
    EVAL_QUESTIONS = [
        {"question": "What is an Oracle tablespace?", "expected_files": ["oracle_tablespaces.md"]},
        {"question": "How does PostgreSQL VACUUM work?", "expected_files": ["postgresql_vacuum.md"]},
        {"question": "What causes ORA-01555 snapshot too old?", "expected_files": ["oracle_undo_ora01555.md"]},
        {"question": "How to improve PostgreSQL performance?", "expected_files": ["postgresql_performance.md"]},
        {"question": "ما هو ORA-01555؟", "expected_files": ["oracle_undo_ora01555.md"]},
        {"question": "Comment fonctionne le VACUUM PostgreSQL ?", "expected_files": ["postgresql_vacuum.md"]},
    ]


def _prefix(model_name: str, texts, is_query: bool):
    low = model_name.lower()
    if "e5" in low:
        tag = "query: " if is_query else "passage: "
        return [tag + t for t in texts]
    if "bge" in low and is_query:
        return ["Represent this sentence for searching relevant passages: " + t for t in texts]
    return list(texts)


def evaluate_model(model_name: str, chunks, k: int) -> dict:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    t0 = time.perf_counter()
    model = SentenceTransformer(model_name)
    texts = [c.text for c in chunks]
    emb = model.encode(
        _prefix(model_name, texts, is_query=False),
        normalize_embeddings=True, batch_size=32, show_progress_bar=True,
    )
    emb = np.asarray(emb, dtype="float32")
    index_time = time.perf_counter() - t0

    hits = 0
    reciprocal = 0.0
    lat = []
    for item in EVAL_QUESTIONS:
        qs = _prefix(model_name, [item["question"]], is_query=True)
        tq = time.perf_counter()
        qv = np.asarray(model.encode(qs, normalize_embeddings=True), dtype="float32")[0]
        sims = emb @ qv
        top_idx = sims.argsort()[::-1][:k]
        lat.append((time.perf_counter() - tq) * 1000)
        expected = {f.lower() for f in item["expected_files"]}
        rank = None
        for r, idx in enumerate(top_idx, start=1):
            if chunks[idx].filename.lower() in expected:
                rank = r
                break
        if rank:
            hits += 1
            reciprocal += 1.0 / rank

    n = len(EVAL_QUESTIONS)
    return {
        "model": model_name,
        "recall_at_k": round(hits / n, 3),
        "mrr": round(reciprocal / n, 3),
        "avg_query_ms": round(sum(lat) / len(lat), 1),
        "index_time_s": round(index_time, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", default=list(MODELS.keys()))
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    print("Chargement du corpus…")
    pages = load_documents(config.DATA_PATH)
    chunks = chunk_pages(pages, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    print(f"{len(chunks)} chunks · {len(EVAL_QUESTIONS)} questions · k={args.k}\n")

    results = []
    for key in args.models:
        name = MODELS.get(key, key)
        print(f"=== {key} ({name}) ===")
        try:
            results.append(evaluate_model(name, chunks, args.k))
        except Exception as exc:
            print(f"  ✗ échec : {exc}")

    results.sort(key=lambda r: (r["recall_at_k"], r["mrr"]), reverse=True)
    print("\n=== Classement (Recall@k, MRR) ===")
    print(f"{'model':40} {'recall':>7} {'mrr':>6} {'q_ms':>7} {'idx_s':>7}")
    for r in results:
        print(f"{r['model']:40} {r['recall_at_k']:>7} {r['mrr']:>6} "
              f"{r['avg_query_ms']:>7} {r['index_time_s']:>7}")
    if results:
        print(f"\n🏆 Meilleur : {results[0]['model']}  "
              f"→ mettez EMBEDDING_MODEL={results[0]['model']} dans .env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
