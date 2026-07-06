# DBA-GPT 🛢️🤖

Assistant intelligent pour DBA (Oracle / PostgreSQL) basé sur le **RAG**.
Il répond **uniquement** à partir de vos documents locaux (PDF, TXT, LOG, MD),
en utilisant **Claude (Anthropic)** comme unique LLM, avec citation des sources
(nom du fichier, page, extrait exact).

## Architecture (v2 — production)

```
PDF / TXT / LOG / MD
      │
      ▼
  Chunking RÉCURSIF (700/150, titres + sections préservés)
      │  métadonnées : filename, page, title, section, chunk_id, source_path
      ▼
  Embeddings locaux normalisés (préfixes adaptés au modèle)
      │
      ▼
  ChromaDB (stockage vectoriel persistant)
      │
      ▼
Question ─► Normalisation (acronymes DBA + fautes de frappe, rapidfuzz)
        ─► Détection de langue (ar/fr/en)
        ─► Retriever dense (ChromaDB top 20)
        ─► FILTRE : similarité ≥ SIMILARITY_THRESHOLD (jamais de source < seuil)
        ─► Reranker cross-encoder (top 5)
        ─► Garde-fou de confiance ──► [LOW] sources=[], repli honnête, PAS d'appel Claude
                                └───► [MEDIUM/HIGH] Claude API
        ─► Réponse + Sources (fichier, page, section, similarité, rerank, PDF page)
           + confidence {level, score} + timing par étape
```

- **Backend** : FastAPI + ChromaDB + sentence-transformers (embeddings **et** reranker)
  + rapidfuzz + langdetect + Anthropic SDK.
- **Frontend** : React (Vite), multilingue **FR / EN / AR** avec **RTL**, badge de
  confiance, « did you mean », latences, ouverture du PDF à la bonne page + surlignage.
- **Anti-hallucination** : double garde-fou → (1) seuil de confiance qui court-circuite
  Claude si aucun passage n'est assez pertinent ; (2) prompt strict « uniquement le contexte ».

### Modèles (multilingue AR/FR/EN)

| Rôle       | Actif (`.env`)                     | Alternative légère (EN, hors-ligne)      |
| ---------- | ----------------------------------- | ----------------------------------------- |
| Embeddings | `intfloat/multilingual-e5-base`     | `BAAI/bge-small-en-v1.5`                  |
| Reranker   | `BAAI/bge-reranker-base`            | `cross-encoder/ms-marco-MiniLM-L-6-v2`    |

Le code applique automatiquement les bons préfixes (`query:`/`passage:` pour e5,
instruction BGE sinon). Après tout changement de `EMBEDDING_MODEL`, relancez
`python scripts/ingest.py` pour reconstruire ChromaDB. Comparez les modèles avec
`python scripts/benchmark_embeddings.py`.

> ℹ️ Réseau HF bridé ? Les gros modèles se téléchargent via le CDN classique en
> désactivant Xet : `HF_HUB_DISABLE_XET=1 python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"`.

## Structure du projet

```
DBA-GPT/
├── backend/
│   ├── main.py                 # API FastAPI (health, chat, source)
│   ├── config.py               # Configuration (.env)
│   ├── rag/
│   │   ├── loader.py           # Chargement PDF/TXT/LOG/MD
│   │   ├── chunker.py          # Découpage en chunks + overlap
│   │   ├── embeddings.py       # Embeddings BGE normalisés
│   │   ├── vectorstore.py      # ChromaDB
│   │   ├── retriever.py        # Recherche sémantique top-k
│   │   ├── claude_client.py    # Client Claude + prompt système strict
│   │   ├── stats.py            # Statistiques RAG (/api/stats)
│   │   └── pipeline.py         # Orchestration RAG
│   ├── scripts/ingest.py       # Reconstruit la base vectorielle
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.jsx, api.js, i18n.js, style.css
│       └── components/ ChatBox.jsx, Message.jsx, Sources.jsx,
│                        SystemStatsPanel.jsx
├── data/                       # ← Déposez vos documents ici
│   ├── oracle/
│   ├── postgresql/
│   └── logs/
├── chroma_db/                  # Base vectorielle (générée)
├── docker-compose.yml
└── README.md
```

## Prérequis

- Python 3.10+
- Node.js 18+
- Une clé API Anthropic (`ANTHROPIC_API_KEY`)

## 1. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # puis éditez .env et renseignez ANTHROPIC_API_KEY
python scripts/ingest.py        # construit la base vectorielle depuis ../data
uvicorn main:app --reload
```

L'API tourne sur http://localhost:8000 (docs interactives : http://localhost:8000/docs).

> ℹ️ **Modèle Claude** : `claude-3-5-sonnet-latest` a été retiré. Le défaut est
> `claude-sonnet-4-6` (rapide et économique). Pour la qualité maximale, mettez
> `CLAUDE_MODEL=claude-opus-4-8` dans `.env`.

## 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Interface sur http://localhost:5173.

## Ajouter vos documents

1. Copiez vos fichiers dans `data/` (sous-dossiers `oracle/`, `postgresql/`, `logs/` ou à la racine).
   Formats supportés : **PDF, TXT, LOG, MD**.
2. Relancez l'ingestion : `python scripts/ingest.py --reset` (dans `backend/`, venv activé).
3. Posez vos questions dans l'interface, en **arabe, français ou anglais**.

Le type de base (`db_type`) est déduit automatiquement du dossier de rangement :
`data/oracle/ → oracle`, `data/postgresql/ → postgresql`, `data/logs/ → logs`.
Il est stocké dans les métadonnées ChromaDB et compté dans la sidebar.

### Ajouter des documents PostgreSQL

1. Déposez vos PDF/MD/TXT PostgreSQL dans **`data/postgresql/`**.
2. Reconstruisez proprement la base vectorielle (**`--reset`** obligatoire après ajout) :

   ```bash
   cd backend
   source venv/bin/activate
   python scripts/ingest.py --reset
   ```

   Le script affiche un diagnostic :

   ```
   Found Oracle files:     8
   Found PostgreSQL files: 5
   Found logs files:       1
   Total files found:      14
   Chunks generated:       50982
   Chroma documents before reset: 13057
   Chroma documents after reset:  0
   Chroma documents after ingestion: 50982
   ```

3. Redémarrez le backend (`uvicorn main:app --reload`).
4. Vérifiez dans la sidebar **« État du système »** que **PostgreSQL** affiche
   `chunks indexés / fichiers détectés` > 0 (ou via `curl http://localhost:8000/api/stats`).

> ⚠️ Ajouter des fichiers **sans** relancer `ingest.py --reset` ne change **rien** :
> ChromaDB n'est pas reconstruit automatiquement. La sidebar affiche alors un
> avertissement « files detected but not indexed ».

### Changer le modèle Claude depuis l'interface

1. Renseignez la liste autorisée dans `backend/.env` :

   ```env
   CLAUDE_MODEL=claude-sonnet-4-6
   AVAILABLE_CLAUDE_MODELS=claude-sonnet-4-6,claude-sonnet-4-5,claude-3-5-sonnet-latest
   ```

2. Dans le header, choisissez le modèle dans le sélecteur **« Modèle Claude »**.
3. Le choix est **mémorisé** (localStorage) et envoyé avec chaque requête `/api/chat`.
   Le backend refuse (400) tout modèle hors `AVAILABLE_CLAUDE_MODELS`.

### Interface

- **Effacer le chat** : bouton dans le header (vide messages, sources, erreurs).
- **Changement de langue** : réinitialise automatiquement le chat (sans relancer de requête).
- **Sidebar « État du système »** : statistiques RAG en temps réel (`/api/stats`).

## Endpoints de l'API

| Méthode | Endpoint                   | Description                											 |
| ------- | -------------------------- | --------------------------------------------- |
| GET     | `/api/health`              | État du service + nombre de documents indexés |
| GET     | `/api/stats`               | Statistiques RAG réelles (documents, chunks, types de base, config, modèles) |
| POST    | `/api/chat`                | Question → réponse + sources (champ `model` optionnel) |
| GET     | `/api/source/{source_id}`  | Ouvre une source (extrait complet du chunk)   |
| GET     | `/api/file/{source_path}`  | Sert le fichier original (PDF) à la bonne page |

### Exemple `POST /api/chat`

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
        "question": "Comment récupérer l espace des lignes mortes en PostgreSQL ?",
        "model": "claude-sonnet-4-6"
      }'
```

- `model` est **optionnel**. S'il est absent → `CLAUDE_MODEL` (défaut) est utilisé.
- Si `model` n'est pas dans `AVAILABLE_CLAUDE_MODELS` → réponse **HTTP 400**.

Réponse :

```json
{
  "answer": "...",
  "model": "claude-sonnet-4-6",
  "sources": [
    {
      "source_id": "postgresql/postgresql_vacuum.md::p1::c0",
      "filename": "postgresql_vacuum.md",
      "page": 1,
      "score": 0.83,
      "excerpt": "La commande VACUUM récupère l'espace..."
    }
  ]
}
```

## Configuration (`.env`)

| Variable                  | Défaut                          | Rôle                                          |
| ------------------------- | ------------------------------- | --------------------------------------------- |
| `ANTHROPIC_API_KEY`       | —                               | Clé API Anthropic (obligatoire)               |
| `CLAUDE_MODEL`            | `claude-sonnet-4-6`             | Modèle Claude par défaut                      |
| `AVAILABLE_CLAUDE_MODELS` | `claude-sonnet-4-6,…`           | Modèles sélectionnables depuis l'UI (CSV)     |
| `RERANK_TOP_K`            | `5`                             | Passages transmis à Claude après reranking    |
| `RETRIEVER_TOP_K`         | `20`                            | Candidats récupérés dans ChromaDB             |
| `EMBEDDING_MODEL`         | `intfloat/multilingual-e5-base` | Modèle d'embedding local                      |
| `RERANKER_MODEL`          | `BAAI/bge-reranker-base`        | Modèle de reranking (cross-encoder)           |
| `USE_RERANKER`            | `true`                          | Active/désactive le reranker                  |
| `SIMILARITY_THRESHOLD`    | `0.70`                          | Seuil de similarité (sous lequel = écarté)    |
| `CHUNK_SIZE`              | `700`                           | Taille des chunks (caractères)                |
| `CHUNK_OVERLAP`           | `150`                           | Chevauchement entre chunks                    |
| `CHROMA_PATH`             | `../chroma_db`                  | Dossier de la base vectorielle                |
| `DATA_PATH`               | `../data`                       | Dossier des documents                         |

## Docker (optionnel)

```bash
export ANTHROPIC_API_KEY=your_api_key_here
docker compose up --build
```

## Multilingue & RTL

- L'utilisateur choisit la langue de l'interface (FR / EN / AR).
- L'arabe active automatiquement l'affichage **RTL**.
- Claude détecte la langue de la question et répond dans cette langue, même si
  les documents sont en anglais.

## Notes anti-hallucination

- La question n'est **jamais** envoyée à Claude sans contexte RAG.
- Si aucun passage pertinent n'est trouvé, DBA-GPT répond explicitement
  « Je n'ai pas trouvé cette information dans les documents fournis. »
- Chaque réponse est accompagnée des sources (fichier + page + extrait exact).

## Déploiement

### Render — service UNIQUE (recommandé)

Tout le projet dans **un seul Web Service** : le backend FastAPI sert les API
`/api/*` **et** le frontend React buildé (`frontend/dist`), fallback SPA vers
`index.html`. Le frontend appelle le **même domaine** (`VITE_API_BASE_URL` vide).

Guide complet, variables et limites Render Free : [`README_RENDER.md`](README_RENDER.md).

- Blueprint : [`render.yaml`](render.yaml) (Render détecte et applique automatiquement).
- Build : `npm run build` (frontend) → `pip install` → `ingest.py --reset` (ChromaDB).
- Start : `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Seul secret à saisir dans le dashboard Render : **`ANTHROPIC_API_KEY`** (`sync:false`).

```bash
# Simuler le mode Render en local (frontend servi par le backend, même port) :
cd frontend && VITE_API_BASE_URL= npm run build
cd ../backend && uvicorn main:app --host 0.0.0.0 --port 8000   # http://localhost:8000
```

Vérifiez via `GET /api/health` (`rag_ready`, `chroma_ready`, `claude_model` ;
aucun secret exposé).

### Alternative : Frontend Vercel + Backend séparé

Possible aussi (frontend statique sur Vercel via [`frontend/vercel.json`](frontend/vercel.json)
avec `VITE_API_BASE_URL=https://votre-backend`, backend sur Render/Railway/VPS —
voir [`backend/README_DEPLOY.md`](backend/README_DEPLOY.md)). Le backend FastAPI +
ChromaDB ne va **jamais** sur Vercel (serverless sans disque persistant).

## 🔒 Sécurité — NEVER COMMIT YOUR API KEY

- **Ne committez JAMAIS votre clé API Anthropic** ni aucun fichier `.env`.
- La clé vit **uniquement** dans `backend/.env` (ignoré par [`.gitignore`](.gitignore)).
- Le repo ne contient que des `*.env.example` **sans vraie clé** (`your_api_key_here`).
- En production, la clé est fournie via les variables d'environnement de la
  plateforme (Render/Railway), jamais dans le code.
- Avant chaque commit, vérifiez :

  ```bash
  git status
  git ls-files | grep -E "\.env$"        # ne doit lister AUCUN .env réel
  git diff --cached | grep -i "sk-ant"   # ne doit RIEN retourner
  ```

  Si une clé apparaît : **STOP**, retirez-la du fichier et de l'index
  (`git rm --cached <fichier>`) avant de committer.
