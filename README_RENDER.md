# DBA-GPT — Déploiement Render (service unique)

Tout le projet tourne dans **un seul Web Service Render** : le backend FastAPI
sert à la fois les API `/api/*` **et** le frontend React buildé (`frontend/dist`),
avec fallback SPA vers `index.html`. **Pas de Vercel.**

---

## Créer le service (étapes exactes)

1. Poussez le repo sur GitHub (voir le push plus bas).
2. Sur https://dashboard.render.com → **New +** → **Web Service**.
3. Connectez le repo GitHub `Melainin2/bcm` (branche `main`).
4. Render détecte [`render.yaml`](render.yaml) → **Apply** (Blueprint).
   Sinon, configurez à la main :
   - **Environment** : Python 3
   - **Build Command** :
     ```
     cd frontend && npm install && npm run build
     cd ../backend && pip install -r requirements.txt
     python scripts/ingest.py --reset
     ```
   - **Start Command** :
     ```
     cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
5. Ajoutez la variable secrète **`ANTHROPIC_API_KEY`** dans le dashboard
   (Environment → Add Environment Variable). ⚠️ **Jamais dans le repo / render.yaml.**
6. Déployez. À la fin, ouvrez l'URL Render : le frontend s'affiche, et
   `https://<app>.onrender.com/api/health` répond `rag_ready: true`.

### Variables d'environnement (dashboard Render)

| Variable                  | Valeur                              | Remarque                          |
| ------------------------- | ----------------------------------- | --------------------------------- |
| `ANTHROPIC_API_KEY`       | *(votre clé)*                       | **secret**, `sync:false`          |
| `CLAUDE_MODEL`            | `claude-sonnet-4-6`                 | via render.yaml                   |
| `AVAILABLE_CLAUDE_MODELS` | `claude-sonnet-4-6,claude-sonnet-5` | via render.yaml                   |
| `DATA_PATH`               | `../data`                           | via render.yaml                   |
| `CHROMA_PATH`             | `../chroma_db`                      | via render.yaml                   |
| `EMBEDDING_MODEL`         | `intfloat/multilingual-e5-base`     | via render.yaml                   |
| `TOP_K`                   | `5`                                 | via render.yaml                   |
| `RETRIEVER_TOP_K`         | `20`                                | via render.yaml                   |
| `SIMILARITY_THRESHOLD`    | `0.70`                              | via render.yaml                   |
| `USE_RERANKER`            | `false`                             | RAM ↓ sur Free (voir plus bas)    |
| `HF_HUB_DISABLE_XET`      | `1`                                 | évite le blocage des téléchargements HF |

Le frontend n'a **pas** besoin de `VITE_API_BASE_URL` (laissé vide → même domaine).

---

## ⚠️ Limites de Render Free — à lire

- **Filesystem éphémère** : ChromaDB généré au **build** est présent dans l'instance
  déployée, mais tout fichier écrit **au runtime** est perdu au redéploiement/redémarrage.
- **Persistent Disk** = plan **payant** uniquement. Sur Free, pas de disque persistant.
- **RAM limitée (512 Mo)** : embeddings e5-base (~1 Go à télécharger) + reranker
  (~1 Go) peuvent dépasser la mémoire. `USE_RERANKER=false` réduit fortement la RAM.
- **Temps/mémoire de build limités** : `ingest.py --reset` sur ~9 000 pages PDF est
  **lourd** (long + gourmand). Il peut échouer sur Free.
- **Mise en veille** : un service Free s'endort après inactivité (premier appel lent).

### Si le build (ingestion) est trop lourd sur Free

Options, par ordre de préférence :

1. **Réduire les documents** : gardez moins de PDF dans `data/` (ex. 1–2 manuels)
   pour que l'ingestion tienne dans les limites Free.
2. **Embedding plus léger** : `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` (EN, ~130 Mo)
   — beaucoup moins de RAM/temps (au prix du multilingue).
3. **Passer payant** : plan Starter + **Persistent Disk**, générer ChromaDB une fois,
   puis retirer `ingest.py --reset` du build (l'index persiste sur le disque).
4. **Stockage externe** : générer `chroma_db/` en local puis le charger depuis un
   stockage objet (S3/GCS) au démarrage.

---

## Local — simuler le mode Render (service unique)

```bash
# 1. Builder le frontend en mode "même domaine" (VITE_API_BASE_URL vide)
cd frontend && VITE_API_BASE_URL= npm run build

# 2. Lancer le backend (qui sert aussi frontend/dist)
cd ../backend && source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000

# 3. Ouvrir http://localhost:8000  → l'UI et les /api/* sont sur le même port.
```

---

## Sécurité

- **Ne committez jamais** `backend/.env` ni `ANTHROPIC_API_KEY`.
- La clé se saisit uniquement dans le dashboard Render (Environment, secret).
- `chroma_db/` reste **git-ignoré** (régénéré au build).
