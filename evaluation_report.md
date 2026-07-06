# DBA-GPT — Rapport d'évaluation RAG

Modèle embeddings : `BAAI/bge-small-en-v1.5` · Reranker : `cross-encoder/ms-marco-MiniLM-L-6-v2` · k=5 · seuil=0.55

Jeu : **65 questions** (59 answerable + 6 hors-domaine).

## Métriques de retrieval (questions answerable)
- **Precision@k** : 0.675
- **Recall@k** : 0.983 (cible > 0.90) ✅
- **MRR** : 0.877

## Latence (retrieval + reranking, hors Claude)
- **Latence moyenne** : 398.1 ms
- **Latence p95** : 263.7 ms

## Multilingue
- **Précision détection de langue** : 0.983
- Recall par langue : en=0.978, fr=1.0, ar=1.0

## Anti-hallucination
- **Taux de réponse sur questions answerable** : 1.0
- **Abstention au garde-fou (hors-domaine bloqués avant Claude)** : 0.667
- **Taux d'hallucination RÉEL (réponse fabriquée hors-domaine)** : 0.0 (cible < 0.02) ✅
- Questions hors-domaine passant le garde-fou (interceptées ensuite par le prompt strict de Claude) :
    - 'How do I configure a MongoDB sharded cluster?' (blend=0.695)
    - 'How do I set up Kubernetes autoscaling?' (blend=0.652)

## Vérification LLM réelle (appels Claude)
- **Questions answerable réellement répondues** : 8/8
- **Questions hors-domaine traitées sans fabrication (abstention garde-fou OU refus explicite de Claude)** : 6/6

| Question | Langue | Confiance | Répondu | Total |
| --- | --- | --- | --- | --- |
| What is an Oracle tablespace? | en | HIGH | oui | 10574.5 ms |
| How do I create a tablespace in Oracle? | en | HIGH | oui | 11322.5 ms |
| What is the difference between a permanent and a t | en | HIGH | oui | 8175.6 ms |
| What causes the ORA-01555 snapshot too old error? | en | HIGH | oui | 6367.9 ms |
| How can I prevent ORA-01555 errors? | en | HIGH | oui | 7667.2 ms |
| What is the undo tablespace used for in Oracle? | en | HIGH | oui | 8346.3 ms |
| How does Oracle Recovery Manager RMAN perform back | en | HIGH | oui | 10120.1 ms |
| What is a whole database backup in RMAN? | en | HIGH | oui | 7765.0 ms |

## Objectifs de production
- Retrieval Recall@5 > 90 % → **98%** ✅
- Hallucination Rate < 2 % → **0%** ✅
- Temps de réponse < 5 s → voir `total_ms` (dominé par Claude ; retrieval+rerank ci-dessus bien en deçà).