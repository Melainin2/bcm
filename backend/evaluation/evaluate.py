"""Évaluation automatique du RAG : Precision@5, Recall@5, MRR, latence, hallucination.

Deux modes :
  - retrieval-only (défaut) : rapide et gratuit. Mesure la qualité du retrieval
    (retriever + reranker) et le taux d'abstention (garde-fou de confiance).
  - --llm N : appelle réellement Claude sur N questions answerable + toutes les
    questions hors-domaine, pour mesurer le taux d'hallucination réel.

Métriques :
  - Precision@k : proportion des k passages dont le fichier ∈ vérité terrain.
  - Recall@k    : proportion de questions avec ≥1 passage pertinent dans le top-k.
  - MRR         : moyenne de 1/rang du premier passage pertinent.
  - Latence     : embedding + retrieval + rerank (et total avec --llm).
  - Hallucination rate : sur les questions HORS domaine, proportion où le système
    N'A PAS abstenu (aurait appelé Claude). Cible < 2 %.
  - Abstention correcte : le système renvoie le repli quand il le doit.

Usage :
    cd backend
    python -m evaluation.evaluate                 # retrieval-only, tout le jeu
    python -m evaluation.evaluate --k 5
    python -m evaluation.evaluate --llm 8         # + appels Claude réels (8 answerable)
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import config  # noqa: E402
from evaluation.questions import all_questions  # noqa: E402
from rag import embeddings, lang, preprocess, reranker  # noqa: E402
from rag.vectorstore import VectorStore  # noqa: E402
from rag.retriever import Retriever  # noqa: E402

REPORT_PATH = Path(__file__).resolve().parent.parent.parent / "evaluation_report.md"


def _files_of(passages: List[Dict]) -> List[str]:
    return [(p.get("filename") or "").lower() for p in passages]


def _confidence(passages: List[Dict]) -> float:
    """Signal de confiance = blend max(reranker, cosinus dense) du meilleur passage."""
    if not passages:
        return 0.0
    top = passages[0]
    return max(float(top.get("rerank_score") or 0.0), float(top.get("score") or 0.0))


# Motifs de refus (repli) dans les 3 langues — pour détecter une abstention LLM.
_REFUSAL_MARKERS = (
    "could not find", "n'ai pas trouvé", "لم أجد",
    "not find relevant", "pas d'information", "aucune information",
    "not contain", "ne contient pas", "لا تحتوي", "لا يحتوي",
)


def _is_refusal(answer: str) -> bool:
    low = (answer or "").lower()
    return any(m.lower() in low for m in _REFUSAL_MARKERS)


def _retrieve_rank(retriever: Retriever, question: str, k: int):
    """Retourne (passages top-k, timings) en reproduisant le pipeline sans Claude."""
    timings = {}
    analysis = preprocess.analyze_query(question)

    t = time.perf_counter()
    candidates = retriever.retrieve(analysis.expanded, config.RETRIEVE_K)
    timings["retrieval_ms"] = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    top = reranker.rerank(analysis.corrected, candidates, top_k=k)
    timings["rerank_ms"] = (time.perf_counter() - t) * 1000
    return top, timings


def run(k: int, llm_n: int) -> Dict:
    store = VectorStore()
    if store.count() == 0:
        raise SystemExit("ChromaDB vide. Lancez d'abord : python scripts/ingest.py")
    retriever = Retriever(store=store)

    questions = all_questions()
    answerable = [q for q in questions if q["answerable"]]
    ood = [q for q in questions if not q["answerable"]]

    precisions, recalls, rr = [], [], []
    latencies = []
    lang_ok = 0
    per_lang = {}

    # --- Retrieval sur les questions answerable ---
    for q in answerable:
        expected = {f.lower() for f in q["expected_files"]}
        top, timings = _retrieve_rank(retriever, q["question"], k)
        files = _files_of(top)
        rel_flags = [f in expected for f in files]
        precisions.append(sum(rel_flags) / max(len(files), 1))
        recalls.append(1.0 if any(rel_flags) else 0.0)
        rank = next((i + 1 for i, f in enumerate(rel_flags) if f), None)
        rr.append(1.0 / rank if rank else 0.0)
        latencies.append(timings["retrieval_ms"] + timings["rerank_ms"])

        detected = lang.detect_language(q["question"])
        lang_ok += 1 if detected == q["lang"] else 0
        per_lang.setdefault(q["lang"], [0, 0])
        per_lang[q["lang"]][0] += 1 if any(rel_flags) else 0
        per_lang[q["lang"]][1] += 1

    # --- Abstention / hallucination (garde-fou de confiance) ---
    # Answerable : le système DOIT répondre (blend >= seuil).
    answerable_answered = 0
    for q in answerable:
        top, _ = _retrieve_rank(retriever, q["question"], k)
        if _confidence(top) >= config.SIMILARITY_THRESHOLD:
            answerable_answered += 1

    # Hors domaine : le système DOIT s'abstenir au garde-fou (blend < seuil).
    ood_abstained = 0
    ood_would_call = []
    for q in ood:
        top, _ = _retrieve_rank(retriever, q["question"], k)
        best = _confidence(top)
        if best < config.SIMILARITY_THRESHOLD:
            ood_abstained += 1
        else:
            ood_would_call.append((q["question"], round(best, 3)))

    n_ans = len(answerable)
    result = {
        "n_questions": len(questions),
        "n_answerable": n_ans,
        "n_ood": len(ood),
        "k": k,
        "precision_at_k": round(statistics.mean(precisions), 3),
        "recall_at_k": round(statistics.mean(recalls), 3),
        "mrr": round(statistics.mean(rr), 3),
        "latency_ms_avg": round(statistics.mean(latencies), 1),
        "latency_ms_p95": round(sorted(latencies)[int(0.95 * len(latencies)) - 1], 1),
        "lang_detect_accuracy": round(lang_ok / n_ans, 3),
        "answerable_answered_rate": round(answerable_answered / n_ans, 3),
        "gate_abstention_rate": round(ood_abstained / max(len(ood), 1), 3),
        # Hallucination réelle : mesurée au niveau de la réponse Claude (voir --llm).
        # Sans --llm, on ne dispose que du garde-fou ; on l'indique comme borne haute.
        "hallucination_rate": None,
        "gate_leak_rate": round(1 - ood_abstained / max(len(ood), 1), 3),
        "ood_would_call": ood_would_call,
        "per_lang_recall": {
            lg: round(v[0] / v[1], 3) for lg, v in per_lang.items()
        },
        "llm_checks": None,
    }

    # --- Vérification LLM réelle (optionnelle) ---
    if llm_n > 0:
        from rag.pipeline import RAGPipeline

        pipe = RAGPipeline.__new__(RAGPipeline)
        pipe.retriever = retriever
        from rag.claude_client import ClaudeClient
        pipe.claude = ClaudeClient()

        checks = {"answerable_ok": 0, "answerable_total": 0,
                  "ood_safe": 0, "ood_total": 0, "ood_hallucinated": 0,
                  "examples": []}
        for q in answerable[:llm_n]:
            res = pipe.answer(q["question"], k)
            answered = res["claude_called"]
            checks["answerable_total"] += 1
            checks["answerable_ok"] += 1 if answered else 0
            checks["examples"].append({
                "q": q["question"], "lang": res["language"],
                "confidence": res["confidence"], "answered": answered,
                "total_ms": res["timings"].get("total_ms"),
            })
        for q in ood:
            res = pipe.answer(q["question"], k)
            checks["ood_total"] += 1
            # « Sûr » = le système n'a PAS fabriqué : soit abstention au garde-fou,
            # soit Claude a explicitement refusé (repli).
            safe = (not res["claude_called"]) or _is_refusal(res["answer"])
            checks["ood_safe"] += 1 if safe else 0
            checks["ood_hallucinated"] += 0 if safe else 1
        result["llm_checks"] = checks
        # Taux d'hallucination RÉEL (au niveau réponse).
        result["hallucination_rate"] = round(
            checks["ood_hallucinated"] / max(checks["ood_total"], 1), 3
        )

    return result


def write_report(r: Dict) -> None:
    def bullet(name, val, target=None, ok=None):
        flag = "" if ok is None else (" ✅" if ok else " ⚠️")
        tgt = f" (cible {target})" if target else ""
        return f"- **{name}** : {val}{tgt}{flag}"

    lines = [
        "# DBA-GPT — Rapport d'évaluation RAG",
        "",
        f"Modèle embeddings : `{config.EMBEDDING_MODEL}` · "
        f"Reranker : `{config.RERANKER_MODEL if config.RERANK_ENABLED else 'désactivé'}` · "
        f"k={r['k']} · seuil={config.SIMILARITY_THRESHOLD}",
        "",
        f"Jeu : **{r['n_questions']} questions** "
        f"({r['n_answerable']} answerable + {r['n_ood']} hors-domaine).",
        "",
        "## Métriques de retrieval (questions answerable)",
        bullet("Precision@k", r["precision_at_k"]),
        bullet("Recall@k", r["recall_at_k"], "> 0.90", r["recall_at_k"] > 0.90),
        bullet("MRR", r["mrr"]),
        "",
        "## Latence (retrieval + reranking, hors Claude)",
        bullet("Latence moyenne", f"{r['latency_ms_avg']} ms"),
        bullet("Latence p95", f"{r['latency_ms_p95']} ms"),
        "",
        "## Multilingue",
        bullet("Précision détection de langue", r["lang_detect_accuracy"]),
        "- Recall par langue : "
        + ", ".join(f"{lg}={v}" for lg, v in r["per_lang_recall"].items()),
        "",
        "## Anti-hallucination",
        bullet("Taux de réponse sur questions answerable", r["answerable_answered_rate"]),
        bullet("Abstention au garde-fou (hors-domaine bloqués avant Claude)",
               r["gate_abstention_rate"]),
        bullet(
            "Taux d'hallucination RÉEL (réponse fabriquée hors-domaine)",
            "n/a (relancer avec --llm)" if r["hallucination_rate"] is None
            else r["hallucination_rate"],
            "< 0.02",
            None if r["hallucination_rate"] is None else r["hallucination_rate"] < 0.02,
        ),
    ]
    if r["ood_would_call"]:
        lines.append(
            "- Questions hors-domaine passant le garde-fou (interceptées ensuite par "
            "le prompt strict de Claude) :"
        )
        for q, s in r["ood_would_call"]:
            lines.append(f"    - {q!r} (blend={s})")

    if r["llm_checks"]:
        c = r["llm_checks"]
        lines += [
            "",
            "## Vérification LLM réelle (appels Claude)",
            bullet("Questions answerable réellement répondues",
                   f"{c['answerable_ok']}/{c['answerable_total']}"),
            bullet("Questions hors-domaine traitées sans fabrication (abstention "
                   "garde-fou OU refus explicite de Claude)",
                   f"{c['ood_safe']}/{c['ood_total']}"),
            "",
            "| Question | Langue | Confiance | Répondu | Total |",
            "| --- | --- | --- | --- | --- |",
        ]
        for e in c["examples"]:
            lines.append(
                f"| {e['q'][:50]} | {e['lang']} | {e['confidence']} | "
                f"{'oui' if e['answered'] else 'non'} | {e['total_ms']} ms |"
            )

    lines += [
        "",
        "## Objectifs de production",
        f"- Retrieval Recall@5 > 90 % → **{r['recall_at_k']*100:.0f}%** "
        f"{'✅' if r['recall_at_k'] > 0.90 else '⚠️'}",
        (
            "- Hallucination Rate < 2 % → **n/a** (relancer avec `--llm`)"
            if r["hallucination_rate"] is None
            else f"- Hallucination Rate < 2 % → **{r['hallucination_rate']*100:.0f}%** "
            f"{'✅' if r['hallucination_rate'] < 0.02 else '⚠️'}"
        ),
        "- Temps de réponse < 5 s → voir `total_ms` (dominé par Claude ; "
        "retrieval+rerank ci-dessus bien en deçà).",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Rapport écrit : {REPORT_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=config.TOP_K)
    parser.add_argument("--llm", type=int, default=0,
                        help="Nombre de questions answerable à vérifier via Claude.")
    args = parser.parse_args()

    print(f"Évaluation (k={args.k}, llm={args.llm})…")
    r = run(args.k, args.llm)
    print("\n=== Résultats ===")
    for key in ("precision_at_k", "recall_at_k", "mrr", "latency_ms_avg",
                "lang_detect_accuracy", "hallucination_rate"):
        print(f"  {key:26} = {r[key]}")
    write_report(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
