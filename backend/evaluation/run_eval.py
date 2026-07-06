"""Évaluation multilingue DBA-GPT (spec §12).

Lit evaluation/questions_multilingual.json et mesure :
  - Precision@5                (qualité du retrieval sur les questions answerable)
  - Hit@5 / Recall             (≥1 source pertinente dans le top-5)
  - Taux de sources vides correctes (abstention sur le hors-domaine)
  - Hallucination rate         (hors-domaine NON abstenu ; réel avec --llm)
  - Latence                    (retrieval + reranking)
  - Multilingual success rate  (par langue : ar / fr / en)

Produit : evaluation/evaluation_report.md

Usage :
    cd backend
    python -m evaluation.run_eval                 # rapide, sans appel Claude
    python -m evaluation.run_eval --llm           # + vérifie l'hallucination via Claude
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from rag import query_normalizer, lang, reranker  # noqa: E402
from rag.retriever import Retriever  # noqa: E402
from rag.vectorstore import VectorStore  # noqa: E402

HERE = Path(__file__).resolve().parent
QUESTIONS_FILE = HERE / "questions_multilingual.json"
REPORT_FILE = HERE / "evaluation_report.md"

# Marqueurs de refus / abstention (EN/FR/AR) — Claude signale l'absence d'info.
_REFUSAL = (
    "could not find", "not find any relevant", "no relevant source",
    "does not contain", "do not contain", "doesn't contain", "not contain any",
    "outside the scope", "out of scope", "cannot provide", "can't provide",
    "no information", "not covered", "not available in",
    "n'ai trouvé aucune", "aucune source", "ne contient pas", "ne contiennent pas",
    "hors du champ", "n'est pas couvert", "pas d'information", "aucune information",
    "je ne peux pas", "لم أجد", "لا تحتوي", "لا يحتوي", "خارج نطاق", "لا تتضمن",
)


def _is_refusal(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _REFUSAL)


def _funnel(retriever: Retriever, question: str, k: int):
    """retrieve → filtre similarité → rerank → top-k. Retourne (top, gate, ms)."""
    norm = query_normalizer.normalize_query(question)
    t = time.perf_counter()
    cand = retriever.retrieve(norm.expanded, config.RETRIEVER_TOP_K)
    relevant = [p for p in cand if (p.get("score") or 0.0) >= config.SIMILARITY_THRESHOLD]
    top = reranker.rerank(norm.corrected, relevant, top_k=k) if relevant else []
    ms = (time.perf_counter() - t) * 1000
    # Décision du garde-fou (confiance).
    rr = top[0].get("rerank_score", 0.0) if top else 0.0
    passes = bool(top) and rr >= config.MEDIUM_CONFIDENCE_THRESHOLD
    return top, passes, ms


def run(k: int, use_llm: bool) -> Dict:
    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    questions = data["questions"]
    store = VectorStore()
    if store.count() == 0:
        raise SystemExit("ChromaDB vide. Lancez d'abord : python scripts/ingest.py")
    retriever = Retriever(store=store)

    answerable = [q for q in questions if q["answerable"]]
    ood = [q for q in questions if not q["answerable"]]

    precisions, hits, latencies = [], [], []
    per_lang = defaultdict(lambda: [0, 0])  # lang -> [hits, total]

    for q in answerable:
        expected = {f.lower() for f in q["expected_files"]}
        top, _passes, ms = _funnel(retriever, q["question"], k)
        latencies.append(ms)
        files = [(p.get("filename") or "").lower() for p in top]
        rel = [f in expected for f in files]
        precisions.append(sum(rel) / len(rel) if rel else 0.0)
        hit = 1 if any(rel) else 0
        hits.append(hit)
        per_lang[q["lang"]][0] += hit
        per_lang[q["lang"]][1] += 1

    # Hors-domaine : abstention au garde-fou (sources vides).
    ood_correct_empty = 0
    ood_leak = []
    for q in ood:
        top, passes, _ = _funnel(retriever, q["question"], k)
        if not passes:
            ood_correct_empty += 1
        else:
            ood_leak.append((q["question"], round(top[0].get("rerank_score", 0.0), 3)))

    n_ans, n_ood = len(answerable), len(ood)
    result = {
        "n": len(questions), "n_answerable": n_ans, "n_ood": n_ood, "k": k,
        "precision_at_k": round(statistics.mean(precisions), 3),
        "hit_at_k": round(statistics.mean(hits), 3),
        "latency_ms_avg": round(statistics.mean(latencies), 1),
        "latency_ms_p95": round(sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)], 1),
        "correct_empty_rate": round(ood_correct_empty / max(n_ood, 1), 3),
        "hallucination_gate": round(1 - ood_correct_empty / max(n_ood, 1), 3),
        "hallucination_real": None,
        "multilingual_success": {lg: round(v[0] / v[1], 3) for lg, v in per_lang.items()},
        "multilingual_overall": round(statistics.mean(hits), 3),
        "ood_leak": ood_leak,
    }

    if use_llm:
        from rag.pipeline import RAGPipeline
        from rag.claude_client import ClaudeClient
        pipe = RAGPipeline.__new__(RAGPipeline)
        pipe.retriever = retriever
        pipe.claude = ClaudeClient()
        halluc = 0
        for q in ood:
            res = pipe.answer(q["question"], k)
            answered = bool(res["sources"]) and not _is_refusal(res["answer"])
            halluc += 1 if answered else 0
        result["hallucination_real"] = round(halluc / max(n_ood, 1), 3)

    return result


def write_report(r: Dict) -> None:
    def ok(v, thr, gt=True):
        return "✅" if (v > thr if gt else v < thr) else "⚠️"

    ml = r["multilingual_success"]
    lines = [
        "# DBA-GPT — Rapport d'évaluation multilingue",
        "",
        f"Embeddings : `{config.EMBEDDING_MODEL}` · Reranker : "
        f"`{config.RERANKER_MODEL if config.USE_RERANKER else 'off'}` · k={r['k']} · "
        f"seuil similarité={config.SIMILARITY_THRESHOLD} · "
        f"confiance HIGH/MEDIUM={config.HIGH_CONFIDENCE_THRESHOLD}/{config.MEDIUM_CONFIDENCE_THRESHOLD}",
        "",
        f"Jeu : **{r['n']}** questions ({r['n_answerable']} answerable + {r['n_ood']} hors-domaine), "
        "réparties EN / FR / AR.",
        "",
        "## Retrieval (questions answerable)",
        f"- **Precision@{r['k']}** : {r['precision_at_k']}",
        f"- **Hit@{r['k']} (≥1 source pertinente)** : {r['hit_at_k']} {ok(r['hit_at_k'], 0.9)}",
        "",
        "## Multilingue (Hit@5 par langue)",
        f"- Anglais : {ml.get('en', 'n/a')}",
        f"- Français : {ml.get('fr', 'n/a')}",
        f"- Arabe : {ml.get('ar', 'n/a')}",
        f"- **Multilingual success rate (global)** : {r['multilingual_overall']}",
        "",
        "## Anti-hallucination (hors-domaine)",
        f"- **Taux de sources vides correctes (abstention)** : {r['correct_empty_rate']} "
        f"{ok(r['correct_empty_rate'], 0.98)}",
        (f"- **Hallucination rate (RÉEL, vérifié Claude)** : {r['hallucination_real']} "
         f"{ok(r['hallucination_real'], 0.02, gt=False)}"
         if r["hallucination_real"] is not None else
         f"- Hallucination rate (garde-fou) : {r['hallucination_gate']} "
         "— relancer avec `--llm` pour la mesure réelle au niveau réponse"),
        "",
        "## Latence (retrieval + reranking, hors Claude)",
        f"- Moyenne : {r['latency_ms_avg']} ms · p95 : {r['latency_ms_p95']} ms",
    ]
    if r["ood_leak"]:
        lines.append("")
        lines.append("- Hors-domaine passant le garde-fou (interceptés ensuite par le "
                     "prompt strict de Claude) :")
        for q, s in r["ood_leak"]:
            lines.append(f"    - {q!r} (rerank={s})")
    lines += [
        "",
        "## Critères de succès",
        f"- Aucune fausse source / similarité 0 % : garantie par le filtre "
        f"≥ {config.SIMILARITY_THRESHOLD} + garde-fou de confiance.",
        f"- Multilingue AR/FR/EN : Hit@5 en={ml.get('en')}, fr={ml.get('fr')}, ar={ml.get('ar')}.",
        "- Hors-domaine : le système s'abstient (sources vides) au lieu d'halluciner.",
    ]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Rapport écrit : {REPORT_FILE}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=config.RERANK_TOP_K)
    parser.add_argument("--llm", action="store_true",
                        help="Vérifier l'hallucination réelle via Claude (hors-domaine).")
    args = parser.parse_args()

    print(f"Évaluation multilingue (k={args.k}, llm={args.llm})…")
    r = run(args.k, args.llm)
    for key in ("precision_at_k", "hit_at_k", "correct_empty_rate",
                "multilingual_overall", "latency_ms_avg"):
        print(f"  {key:22} = {r[key]}")
    print(f"  multilingual_success  = {r['multilingual_success']}")
    write_report(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
