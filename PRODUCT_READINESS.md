# DBA-GPT — Product Readiness

Guide opérationnel du produit DBA-GPT : architecture, exploitation, tests,
limites connues et feuille de route. Complète le [README](README.md).

---

## 1. Architecture

```
                    ┌─────────────────────────────────────────────┐
   data/            │  Ingestion (scripts/ingest.py)              │
   ├── oracle/      │   loader → chunker → embeddings → ChromaDB   │
   ├── postgresql/  │   (db_type déduit du dossier de rangement)  │
   └── logs/        └─────────────────────────────────────────────┘
                                      │
                                      ▼
                             ChromaDB (persistant)
                                      │
  Frontend React (Vite)              ▼
  ├── Header : langue · modèle Claude · Effacer le chat
  ├── Sidebar : État du système (GET /api/stats)
  └── Chat  ──►  POST /api/chat {question, model} ──► FastAPI
                                      │
                    Normalisation → langue → retriever (top 20)
                    → filtre similarité ≥ seuil → reranker (top 5)
                    → garde-fou de confiance
                       ├─ LOW  : pas d'appel Claude, sources = []
                       └─ MED/HIGH : Claude API (modèle validé)
                                      │
                                      ▼
                    Réponse + sources (fichier, page, extrait)
                    + confidence {level, score} + timing
```

**Stack** : FastAPI · ChromaDB · sentence-transformers (embeddings + reranker) ·
Anthropic Claude (unique LLM) · React (Vite).

**Anti-hallucination** : (1) filtre de similarité + garde-fou de confiance qui
court-circuite Claude si aucun passage n'est assez pertinent ; (2) prompt système
strict « uniquement le contexte ». Aucune source sous le seuil n'est jamais
affichée — **pas de sources « fake »**.

---

## 2. Ajouter des documents (Oracle / PostgreSQL / logs)

| Type       | Dossier             | `db_type` déduit |
| ---------- | ------------------- | ---------------- |
| Oracle     | `data/oracle/`      | `oracle`         |
| PostgreSQL | `data/postgresql/`  | `postgresql`     |
| Logs       | `data/logs/`        | `logs`           |
| Autre      | racine `data/`      | `unknown`        |

Formats supportés : **PDF, TXT, LOG, MD**.

```bash
# 1. Déposer les fichiers dans le bon sous-dossier de data/
# 2. Reconstruire la base (--reset obligatoire après ajout)
cd backend && source venv/bin/activate
python scripts/ingest.py --reset
# 3. Redémarrer le backend
uvicorn main:app --reload
# 4. Vérifier
curl http://localhost:8000/api/stats   # indexed_postgresql_chunks > 0 attendu
```

Chaque chunk indexé porte les métadonnées :
`filename, source_path, page, chunk_id, db_type, file_type, indexed_at`.

---

## 3. Reconstruire ChromaDB

```bash
cd backend && source venv/bin/activate
python scripts/ingest.py --reset   # reconstruction complète (reset + ré-indexation)
python scripts/ingest.py           # idem (reset par défaut)
python scripts/ingest.py --keep    # ajout sans réinitialiser la collection
```

Reconstruire avec `--reset` est **obligatoire** après tout changement de :
`EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, ou ajout/suppression de documents.
Sans reconstruction, les nouveaux fichiers ne sont **pas** indexés (la sidebar
affiche alors « files detected but not indexed »).

---

## 4. Changer le modèle Claude

Deux niveaux :

- **Défaut serveur** — `CLAUDE_MODEL` dans `backend/.env`.
- **Sélection utilisateur** — sélecteur « Modèle Claude » dans le header.
  Le choix est mémorisé (localStorage) et envoyé dans chaque requête `/api/chat`.

Contrôle d'accès : seuls les modèles listés dans `AVAILABLE_CLAUDE_MODELS`
(CSV, `backend/.env`) sont acceptés. Tout autre modèle → **HTTP 400**.

```env
CLAUDE_MODEL=claude-sonnet-4-6
AVAILABLE_CLAUDE_MODELS=claude-sonnet-4-6,claude-sonnet-4-5,claude-3-5-sonnet-latest
```

---

## 5. Tester

```bash
# Backend (aucun téléchargement de modèle ni appel Claude : stubs déterministes)
cd backend && source venv/bin/activate
pytest -q

# Frontend (build de production)
cd frontend
npm run build
```

Vérifications manuelles rapides :

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/stats
# Modèle valide (appelle Claude) :
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"question":"What is VACUUM in PostgreSQL?","model":"claude-sonnet-4-6"}'
# Modèle invalide → 400 :
curl -i -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
  -d '{"question":"x","model":"gpt-4"}'
```

Côté interface : envoyer une question, cliquer **Effacer le chat**, changer la
langue (le chat se vide), changer de modèle et vérifier la sidebar.

---

## 6. Limites actuelles

- **Pas d'historique conversationnel** : chaque question est indépendante
  (pas de mémoire multi-tours côté RAG).
- **`db_type` des documents déjà indexés** : les stats de documents sont dérivées
  du dossier `data/` (fiable) ; les chunks pré-existants n'ont le champ `db_type`
  en métadonnées qu'après une ré-ingestion.
- **Ingestion synchrone** : `ingest.py` est un script hors-ligne, pas d'upload
  de documents depuis l'interface.
- **Compteur `total_documents`** = nombre de fichiers sources (pas de dédoublonnage
  de contenu).
- **Coût Claude** : chaque question MEDIUM/HIGH déclenche un appel API facturé.
- **Modèles locaux** : embeddings + reranker multilingues (~1 Go chacun) à
  télécharger au premier lancement.

---

## 7. Prochaines améliorations

- Upload de documents + ré-indexation incrémentale depuis l'interface.
- Historique de conversation persistant (multi-tours).
- Filtrage des recherches par `db_type` (répondre uniquement sur Oracle *ou* PostgreSQL).
- Streaming de la réponse Claude (SSE) pour un rendu progressif.
- Authentification / multi-utilisateurs.
- Cache des réponses fréquentes.
- Observabilité : métriques Prometheus, traces de latence par étape.
