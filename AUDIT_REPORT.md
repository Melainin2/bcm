# DBA-GPT — Rapport d'audit RAG (avant refonte production)

Date : 2026-07-04 · Auditeur : Senior AI Engineer / Architecte RAG
État initial : FastAPI + React + ChromaDB + BGE-small + Claude · 10 619 chunks · 11 documents

Ce rapport analyse le système **tel qu'il existait avant la refonte**. Chaque
problème est suivi de sa **cause racine** et de l'**amélioration** appliquée
(voir `FINAL_REPORT.md` pour l'implémentation).

---

## 0. Synthèse — verdict

Le système de départ **fonctionne** (ingestion, retrieval dense + boost lexical,
Claude, sources, FR/EN/AR, RTL). C'est une base honnête. Mais il présente
**8 défauts bloquants** pour un niveau production « 10/10 », dont un
**défaut de conception majeur** : l'embedding est un modèle **anglais uniquement**
alors que le produit promet un retrieval cross-lingue (questions AR/FR sur des
docs EN). Note de départ estimée : **5.5 / 10**.

| Axe | Avant | Cible |
| --- | ----- | ----- |
| Qualité retrieval (mono-langue EN) | Correct | Excellent |
| Retrieval cross-lingue (AR/FR → EN) | **Faible** | Excellent |
| Anti-hallucination (garde-fou dur) | Partiel (prompt only) | Fort (seuil + prompt) |
| Robustesse fautes de frappe / acronymes | **Absente** | Forte |
| Reranking | **Absent** | Cross-encoder |
| Confiance exposée | **Absente** | HIGH/MED/LOW |
| Observabilité (latences) | **Absente** | Par étape |
| Évaluation automatique | **Absente** | Precision@k / MRR / halluc. |
| Ouverture PDF à la page + surlignage | **Absente** | Oui |

---

## 1. Architecture & pipeline — vue d'ensemble

```
loader.py → chunker.py → embeddings.py → vectorstore.py (Chroma)
                                              ↑
question → retriever.py (dense + boost lexical) → claude_client.py → pipeline.py → main.py
```

**Points forts constatés**
- Séparation claire des modules (`rag/`), config centralisée par `.env`.
- Retriever **hybride** artisanal : pool dense élargi + bonus lexical + garde-fou
  `where_document $contains` pour les codes d'erreur (ORA-01555). Bonne intuition.
- Gestion robuste des PDF chiffrés/corrompus dans `loader.py`.
- Frontend multilingue FR/EN/AR avec RTL et détection de direction par texte.
- Test de fumée qui mocke embeddings + Claude (bon réflexe d'isolation).

---

## 2. Problèmes détectés (cause → correctif)

### P1 — 🔴 CRITIQUE : embedding **anglais uniquement** (`BAAI/bge-small-en-v1.5`)
- **Symptôme** : une question en arabe/français sur une doc anglaise repose
  presque uniquement sur le boost lexical (codes d'erreur), pas sur le sens.
  Une question AR reformulée sans mot-clé anglais retrouve mal les passages.
- **Cause** : `bge-small-en-v1.5` n'a pas d'espace vectoriel partagé entre
  langues. Le produit **promet** pourtant un retrieval cross-lingue.
- **Correctif** : passage à **`intfloat/multilingual-e5-base`** (100+ langues,
  dont l'arabe), avec un **banc d'essai** (`scripts/benchmark_embeddings.py`)
  comparant bge-small, bge-base, e5-base, e5-large et choisissant le meilleur
  par score de retrieval réel.

### P2 — 🔴 Aucun reranking
- **Symptôme** : le top-5 dense/lexical contient parfois des passages
  thématiquement proches mais non pertinents ; Claude reçoit du bruit.
- **Cause** : le classement final repose sur la similarité cosinus + heuristique
  lexicale, sans modèle de pertinence question↔passage.
- **Correctif** : **cross-encoder `BAAI/bge-reranker-base`**. Pipeline
  `retrieve 15 → rerank → top 5 → Claude`.

### P3 — 🔴 Pas de garde-fou dur anti-hallucination
- **Symptôme** : même hors-sujet, on envoie toujours le top-k à Claude ; la seule
  barrière est le prompt. Risque d'« hallucination polie ».
- **Cause** : absence de **seuil de confiance**. `pipeline.answer()` appelle
  toujours `claude.generate()`.
- **Correctif** : `SIMILARITY_THRESHOLD` (défaut 0.80 sur le score reranker
  normalisé). Si aucun passage ne dépasse le seuil → **on n'appelle pas Claude**,
  on renvoie le message de repli et `confidence = LOW`.

### P4 — 🟠 Aucune robustesse fautes de frappe / acronymes
- **Symptôme** : `postgressql`, `orcale`, `tablspace`, `ARW` (pour AWR) dégradent
  le retrieval ; les acronymes non développés matchent mal des docs qui écrivent
  la forme longue.
- **Cause** : la question part brute vers l'embedding, sans normalisation.
- **Correctif** : module `preprocess.py` — dictionnaire d'acronymes DBA (AWR, ASM,
  RMAN, SGA, PGA, ASH, RAC, CDB, PDB, WAL, VACUUM, MVCC, …) avec **expansion**,
  correction orthographique **rapidfuzz** (`postgressql → postgresql`), et
  suggestion « Did you mean AWR ? ».

### P5 — 🟠 Chunking par fenêtre glissante « plate »
- **Symptôme** : coupe au caractère/espace sans respecter titres, sections, listes.
  Un tableau ou une procédure numérotée peut être tranché en plein milieu.
- **Cause** : `chunk_text()` est un simple `while` sur les offsets.
- **Correctif** : **splitter récursif** (séparateurs hiérarchiques
  `\n\n` → `\n` → phrase → mot), `chunk_size=700`, `overlap=150`, détection de
  **titre/section** (en-têtes Markdown, lignes ALL-CAPS de PDF), métadonnées
  enrichies : `filename, page, title, section, chunk_id, source_path`.

### P6 — 🟠 Pas de détection de langue explicite
- **Symptôme** : on demande à Claude de « répondre dans la langue de la question »,
  mais rien ne le garantit ni ne le mesure ; l'UI ne connaît pas la langue.
- **Cause** : aucune détection côté serveur.
- **Correctif** : `langdetect` → `ar/fr/en`, injecté dans le prompt et renvoyé
  par l'API.

### P7 — 🟠 Aucune observabilité (latences)
- **Symptôme** : impossible de savoir où part le temps (12,7 s moyen mesurés).
- **Cause** : pas d'instrumentation.
- **Correctif** : chronométrage **par étape** (embedding, retrieval, reranking,
  Claude, total), loggé et renvoyé dans la réponse API (`timings`).

### P8 — 🟠 Confiance non exposée + sources incomplètes
- **Symptôme** : l'UI montre un « score » (cosinus) mais aucun niveau de confiance
  global ; pas d'ouverture du PDF à la bonne page, pas de surlignage.
- **Cause** : le pipeline ne calcule pas de confiance ; pas d'endpoint de service
  de fichier PDF.
- **Correctif** : `confidence` (HIGH/MED/LOW) dans l'API ; endpoint
  `/api/file/{path}` servant le PDF, ouverture front `#page=N` + surlignage de
  l'extrait.

### Défauts mineurs
- `api.js` : fallback `http://localhost:8000` alors que le backend tourne sur
  **8001** (le `.env` corrige, mais le défaut est trompeur). → aligné sur 8001.
- `@app.on_event("startup")` : API dépréciée FastAPI → migration `lifespan`.
- Aucune suite **pytest** (juste un script de fumée). → `tests/` pytest complet.
- Le score affiché est la **distance cosinus**, sensible au modèle ; il faut le
  compléter par le score reranker (pertinence réelle).

---

## 3. Améliorations proposées (feuille de route appliquée)

1. Chunking récursif + métadonnées riches (P5).
2. Embeddings multilingues e5-base + banc d'essai auto-sélection (P1).
3. Reranker cross-encoder bge-reranker-base (P2).
4. Seuil de confiance + court-circuit Claude (P3).
5. Préprocessing requête : acronymes + fautes de frappe rapidfuzz (P4).
6. Détection de langue + prompt strict avec confiance (P3, P6).
7. Observabilité par étape (P7).
8. Frontend : badge de confiance, latences, « did you mean », PDF page + surlignage (P8).
9. `evaluation/` : Precision@5, Recall@5, MRR, latence, taux d'hallucination + rapport.
10. `tests/` pytest : ingestion, chunking, embeddings, retriever, reranker, preprocessing, API.

**Aucune fonctionnalité existante n'est supprimée** — uniquement enrichie.
