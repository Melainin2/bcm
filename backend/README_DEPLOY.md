# DBA-GPT — Déploiement du backend

Le backend **FastAPI + ChromaDB** ne peut **pas** être déployé sur Vercel
(Vercel = fonctions serverless éphémères, sans stockage disque persistant pour
ChromaDB ni processus long). Déployez-le sur une plateforme avec disque
persistant : **Render**, **Railway**, **Fly.io**, ou un **VPS**.

> Le frontend React, lui, va sur Vercel (voir la racine du repo). Il pointe vers
> l'URL publique de ce backend via la variable `VITE_API_BASE_URL`.

---

## Variables d'environnement requises

| Variable                  | Obligatoire | Exemple                              |
| ------------------------- | ----------- | ------------------------------------ |
| `ANTHROPIC_API_KEY`       | ✅          | votre clé Anthropic (⚠️ secret, jamais commité) |
| `CLAUDE_MODEL`            | ✅          | `claude-sonnet-4-6`                  |
| `AVAILABLE_CLAUDE_MODELS` | ✅          | `claude-sonnet-4-6,claude-sonnet-5`  |
| `DATA_PATH`               | ✅          | `../data`                            |
| `CHROMA_PATH`             | ✅          | `../chroma_db`                       |
| `EMBEDDING_MODEL`         | recommandé  | `intfloat/multilingual-e5-base`      |
| `USE_RERANKER`            | recommandé  | `true`                               |
| `CORS_ORIGINS`            | ✅ (prod)   | `https://votre-app.vercel.app`       |

Définissez ces variables dans le dashboard de la plateforme (jamais dans le repo).
En production, `CORS_ORIGINS` **doit** contenir l'URL Vercel du frontend.

---

## Lancer en production

```bash
pip install -r requirements.txt
python scripts/ingest.py --reset          # construit ChromaDB depuis data/
uvicorn main:app --host 0.0.0.0 --port $PORT
```

- `--reset` reconstruit l'index à chaque nouveau jeu de documents.
- `$PORT` est fourni par la plateforme (Render/Railway l'injectent).
- Le premier lancement télécharge les modèles d'embedding + reranker (~1–2 Go) ;
  prévoyez un disque persistant et un cache HuggingFace pour éviter de re-télécharger.

### Exemple : Render (`render.yaml` indicatif)

```yaml
services:
  - type: web
    name: dba-gpt-backend
    env: python
    buildCommand: "pip install -r backend/requirements.txt"
    startCommand: "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT"
    disk:
      name: chroma
      mountPath: /opt/render/project/src/chroma_db
      sizeGB: 5
```

---

## Vérifier le déploiement — `GET /api/health`

```bash
curl https://votre-backend/api/health
```

Réponse (aucun secret exposé — seulement un booléen `api_key_configured`) :

```json
{
  "status": "ok",
  "rag_ready": true,
  "chroma_ready": true,
  "documents_indexed": 50982,
  "claude_model": "claude-sonnet-4-6",
  "available_claude_models": ["claude-sonnet-4-6", "claude-sonnet-5"],
  "api_key_configured": true
}
```

- `rag_ready` : ChromaDB chargé **et** au moins un document indexé.
- `chroma_ready` : la base vectorielle est accessible.
- `api_key_configured` : booléen — la clé n'est **jamais** renvoyée en clair.

---

## Sécurité

- **Ne committez jamais `backend/.env`** ni `ANTHROPIC_API_KEY` (voir `.gitignore`).
- Utilisez uniquement `backend/.env.example` (sans vraie clé) dans le repo.
- Restreignez `CORS_ORIGINS` à l'URL exacte du frontend en production.
