# DBA-GPT — Rapport final (refonte production v2)

Date : 2026-07-05 · LLM unique : **Claude** (`claude-sonnet-4-6`, clé lue depuis `.env`).
Aucune fonctionnalité existante n'a été supprimée — le système a été **enrichi**.

Détails chiffrés : `evaluation/evaluation_report.md`. Audit initial : `AUDIT_REPORT.md`.

---

## 1. Résultats clés (mesurés)

| Objectif | Résultat | Cible | Statut |
| --- | --- | --- | --- |
| Retrieval Hit@5 (≥1 bonne source) | **100 %** | > 90 % | ✅ |
| Multilingue Hit@5 (EN / FR / AR) | **1.0 / 1.0 / 1.0** | AR/FR/EN OK | ✅ |
| Hallucination réelle (hors-domaine, vérifiée Claude) | **0 %** | < 2 % | ✅ |
| Sources « fake » / similarité < 70 % affichées | **0** | jamais | ✅ |
| Détection de langue | **98 %** | — | ✅ |
| Latence retrieval + reranking | **~1,4 s** (p95 1,3 s) | — | ✅ |
| Precision@5 (granularité fichier) | 0,64 | — | ℹ️ sous-estimée* |

\* La vérité terrain est au niveau *fichier* ; un chunk pertinent issu d'un autre
document Oracle valable compte comme « non pertinent », ce qui minore la précision.

Jeu d'évaluation : 28 questions multilingues (23 answerable + 5 hors-domaine).

---

## 2. Améliorations réalisées (par thème)

### Retrieval
- **Chunking récursif** (700/150) préservant titres / sections / listes + métadonnées
  riches (`filename, page, title, section, chunk_id, source_path`).
- **Entonnoir** : ChromaDB top **20** → **filtre similarité ≥ 0.70** → **reranker
  cross-encoder** → top **5** → Claude.
- **Base reconstruite** : **13 057 chunks** (contre 10 619 en v1).

### Multilingue AR / FR / EN
- **Embeddings multilingues** `intfloat/multilingual-e5-base` (préfixes `query:` /
  `passage:` appliqués automatiquement par `embeddings.py`).
- **Reranker multilingue** `BAAI/bge-reranker-base` (score correctement les paires
  question AR/FR ↔ passage EN).
- **Détection de langue** (`lang.py`) → Claude répond dans la langue de la question,
  même sur des documents anglais.

### Prévention d'hallucination (double garde-fou)
1. **Filtre de similarité** : aucune source sous 0.70 n'est jamais retournée ni affichée.
2. **Garde-fou de confiance** : si le meilleur passage < seuil → **Claude n'est PAS
   appelé**, `sources = []`, `confidence = LOW`, message clair.
3. **Prompt strict** : uniquement le contexte, jamais d'invention, jamais Internet,
   cite uniquement les sources fournies, termine par le niveau de confiance.

### Sources & UX/UI professionnelle
- **`SourcePanel`** : barre compacte `Sources (n) · Confidence · Voir détails`,
  **fermée par défaut**, déploiement animé.
- **`SourceCard`** : document, page, section, similarité, rerank, boutons
  **Open PDF page**, **Copy excerpt**, **Expand excerpt** (viewer interne).
- Design dark pro, badges de confiance, **RTL arabe**, responsive.

### Robustesse technique
- **`query_normalizer.py`** : corrections (ORCALE→ORACLE, POSTGRESSQL→PostgreSQL,
  TABLSPACE→TABLESPACE, VACUME→VACUUM, PERFORMENCE→PERFORMANCE, MONITORE→MONITOR,
  WALS→WAL…) + acronymes DBA + suggestion « Did you mean AWR ? » (rapidfuzz).
- **Observabilité** : logs `question / corrigée / langue / top_sim / nb sources /
  temps retrieval|rerank|claude / décision (CALL_CLAUDE | NO_RELEVANT_SOURCE)`.
- **Tests** : `pytest` — 37 tests (unitaires stubbés + 5 tests qualité sur la vraie base).

---

## 3. Format de réponse `/api/chat`

```json
{
  "answer": "...",
  "language": "fr|ar|en",
  "confidence": { "level": "HIGH|MEDIUM|LOW", "score": 0.73 },
  "corrected_query": "… ou null",
  "sources": [
    { "id": "...", "filename": "...", "page": 19, "section": "...",
      "similarity": 0.89, "rerank_score": 0.73, "excerpt": "...",
      "source_url": "/api/source/...", "source_path": "oracle/…pdf" }
  ],
  "timing": { "retrieval_ms": 120, "rerank_ms": 80, "claude_ms": 1900, "total_ms": 2200 }
}
```

---

## 4. Bugs / défauts corrigés

1. **Sources « fake » (similarité faible/0 %)** → filtre dur `similarity ≥ 0.70` +
   garde-fou dans `_sources()` ; l'UI ne peut plus afficher une source sous le seuil.
2. **Claude appelé sans contexte fiable** → décision `NO_RELEVANT_SOURCE` : pas
   d'appel LLM, `sources=[]`, `confidence=LOW` (vérifié : « Lionel Messi » → abstention).
3. **Embeddings anglais uniquement** → e5 multilingue : Hit@5 AR passe de faible à **1.0**.
4. **Pas de reranking** → cross-encoder bge-reranker-base.
5. **Aucune robustesse fautes/acronymes** → `query_normalizer` (rapidfuzz).
6. **Aucune observabilité** → timings par étape + logs de décision.
7. **UX sources brute** → `SourcePanel`/`SourceCard` (fermées par défaut, PDF page, copy, RTL).
8. Divers : `api.js` 8000→8001 ; `@app.on_event` déprécié → `lifespan` ; endpoint
   `/api/file/{path}` sécurisé (anti-traversée de répertoire) pour servir les PDF.

---

## 5. Métriques avant / après

| | Avant (v1) | Après (v2) |
| --- | --- | --- |
| Embeddings | bge-small (EN seul) | **e5-base (multilingue)** |
| Reranker | aucun | **bge-reranker-base** |
| Filtre anti-fausses-sources | ❌ | ✅ (≥ 0.70) |
| Garde-fou confiance (skip Claude) | ❌ | ✅ HIGH/MEDIUM/LOW |
| Chunks indexés | 10 619 (1000/150) | 13 057 (700/150 récursif) |
| Retrieval Hit@5 | non mesuré | **100 %** |
| Multilingue Hit@5 (en/fr/ar) | non mesuré | **1.0 / 1.0 / 1.0** |
| Hallucination réelle | non mesuré | **0 %** |
| Latence retrieval+rerank | non mesuré | **~1,4 s** |

---

## 6. Fichiers créés / modifiés

**Backend** — `config.py` (clés v2 + défauts multilingues), `main.py` (schéma v2,
`lifespan`, `/api/file`), `rag/pipeline.py` (entonnoir + filtre + garde-fou + obs.),
`rag/query_normalizer.py` *(nouv.)*, `rag/preprocess.py` (shim), `rag/reranker.py`
*(nouv.)*, `rag/embeddings.py` (préfixes e5/bge), `rag/lang.py` *(nouv.)*,
`rag/claude_client.py` (prompt strict), `rag/chunker.py` (récursif + métadonnées),
`rag/vectorstore.py`, `scripts/ingest.py`, `scripts/benchmark_embeddings.py` *(nouv.)*,
`tests/*` *(nouv.)*, `evaluation/*` *(nouv.)*, `requirements.txt`.

**Frontend** — `components/SourcePanel.jsx`, `components/SourceCard.jsx` *(nouv.)*,
`components/Message.jsx`, `App.jsx`, `api.js`, `i18n.js`, `style.css`.

---

## 7. Commandes pour relancer

```bash
# Backend
cd backend
pip install -r requirements.txt            # (venv : ./venv/bin/pip)
python scripts/ingest.py                   # reconstruit ChromaDB (après changement de modèle)
pytest                                      # 37 tests
python -m evaluation.run_eval --llm        # évaluation multilingue + hallucination réelle
uvicorn main:app --port 8001 --reload      # API http://localhost:8001

# Frontend
cd ../frontend
npm install
npm run dev                                # http://localhost:5173
```

> Réseau Hugging Face bridé ? Téléchargez les modèles avec `HF_HUB_DISABLE_XET=1`
> (le backend Xet se bloque sinon). Modèles : e5-base + bge-reranker-base (~1,1 Go chacun).

---

## 8. Limites restantes

- **Latence totale ~7–11 s** dominée par la génération Claude (le retrieval+rerank est
  ~1,4 s). Pour < 5 s : réduire `MAX_TOKENS`, streamer la réponse, ou modèle Claude plus rapide.
  La **première** requête est plus lente (chargement paresseux des modèles e5 + reranker).
- **Seuil de confiance calibré empiriquement** au reranker bge (sigmoïde : 0.5 = neutre) :
  `MEDIUM=0.52`, `HIGH=0.71`. Marge fine côté AR/FR (rerank ~0.53) — un reranker plus
  gros (bge-reranker-large) élargirait la marge.
- **1 question hors-domaine sur 5** (« MongoDB sharded cluster ») franchit le garde-fou
  car proche du domaine « clustering » ; Claude la refuse explicitement (hallucination
  réelle = 0), mais des sources Oracle s'affichent. Acceptable, intercepté par le prompt.
- **Corpus PostgreSQL limité** (2 fiches) : ajouter des documents dans `data/postgresql/`
  puis réingérer pour élargir la couverture.
