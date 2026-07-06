# DBA-GPT — Rapport d'évaluation multilingue

Embeddings : `intfloat/multilingual-e5-base` · Reranker : `BAAI/bge-reranker-base` · k=5 · seuil similarité=0.7 · confiance HIGH/MEDIUM=0.71/0.52

Jeu : **28** questions (23 answerable + 5 hors-domaine), réparties EN / FR / AR.

## Retrieval (questions answerable)
- **Precision@5** : 0.643
- **Hit@5 (≥1 source pertinente)** : 1 ✅

## Multilingue (Hit@5 par langue)
- Anglais : 1.0
- Français : 1.0
- Arabe : 1.0
- **Multilingual success rate (global)** : 1

## Anti-hallucination (hors-domaine)
- **Taux de sources vides correctes (abstention)** : 0.8 ⚠️
- **Hallucination rate (RÉEL, vérifié Claude)** : 0.0 ✅

## Latence (retrieval + reranking, hors Claude)
- Moyenne : 1412.9 ms · p95 : 1248.1 ms

- Hors-domaine passant le garde-fou (interceptés ensuite par le prompt strict de Claude) :
    - 'How do I configure a MongoDB sharded cluster?' (rerank=0.701)

## Critères de succès
- Aucune fausse source / similarité 0 % : garantie par le filtre ≥ 0.7 + garde-fou de confiance.
- Multilingue AR/FR/EN : Hit@5 en=1.0, fr=1.0, ar=1.0.
- Hors-domaine : le système s'abstient (sources vides) au lieu d'halluciner.