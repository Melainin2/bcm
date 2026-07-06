# Rapport de validation bout-en-bout — DBA-GPT

Date : 2026-07-04 · Modèle Claude : `claude-sonnet-4-6` · Embeddings : `BAAI/bge-small-en-v1.5`

## 1. Indexation

| Métrique                | Valeur                                             |
| ----------------------- | -------------------------------------------------- |
| Documents indexés       | **11** (6 PDF Oracle + 4 MD + 1 LOG)               |
| Pages extraites         | **3 453**                                          |
| Chunks indexés          | **10 619**                                         |
| Base vectorielle        | `chroma_db/chroma.sqlite3` (~88 Mo) créée ✅        |
| Durée d'ingestion       | ~5 min 52 s (embeddings CPU)                        |

Détail par document :

| Fichier                                             | pages | chunks |
| --------------------------------------------------- | ----: | -----: |
| database-administrators-guide.pdf                   |  1647 |   5034 |
| high-availability-overview-and-best-practices.pdf   |   812 |   2877 |
| database-backup-and-recovery-reference.pdf          |   525 |   1490 |
| database-performance-tuning-guide.pdf               |   380 |   1067 |
| db-19c-architecture.pdf                             |    40 |     96 |
| diag-pack-ow09-133950.pdf                           |    44 |     44 |
| oracle_undo_ora01555.md / oracle_tablespaces.md     |     2 |      5 |
| postgresql_performance.md / postgresql_vacuum.md    |     2 |      5 |
| alert_sample.log                                    |     1 |      1 |

## 2. Endpoints API (backend testé sur le port 8001)

- `GET  /api/health` → `{status: ok, documents_indexed: 10619, api_key_configured: true}` ✅
- `POST /api/chat` → réponse + sources (fichier, page, extrait, score) ✅
- `GET  /api/source/{id}` → extrait exact du chunk (997 caractères) ✅ ; 404 si inconnu ✅

## 3. Tests RAG réels (appels Claude réels)

| Question                                | Réponse | Sources principales                              |
| --------------------------------------- | :-----: | ------------------------------------------------ |
| What is an Oracle tablespace?           | ✅       | oracle_tablespaces.md, database-administrators-guide.pdf p598 |
| How can I improve PostgreSQL performance? | ✅     | postgresql_performance.md, database-performance-tuning-guide.pdf p56 |
| What is ORA-01555?                      | ✅       | oracle_undo_ora01555.md p1 (après correctif retriever) |
| ما هو ORA-01555 ؟ (arabe)               | ✅       | oracle_undo_ora01555.md p1 (réponse en arabe, RTL) |

**Temps moyen de réponse : ~12,7 s** (14,8 / 10,0 / 8,2 / 17,7 s).

Pour chaque réponse : bons chunks récupérés ✅, appel réel à Claude ✅, sources
affichées avec **nom de fichier + numéro de page + extrait exact** ✅.

## 4. Interface & multilingue

- Anglais / Français : LTR ✅
- Arabe : RTL complet (layout miroir, réponse en arabe) ✅
- RAG cross-lingue : documents anglais → réponse arabe correcte ✅
- Bouton « Ouvrir la source » : affiche l'extrait exact via `/api/source/{id}` ✅

## 5. Bugs détectés et corrigés

1. **PDF chiffré (AES) faisant planter toute l'ingestion**
   - Cause : `pypdf` requiert `cryptography` pour l'AES, et l'itération paresseuse
     des pages levait l'exception hors du bloc `try`.
   - Correctif : ajout de `cryptography` aux dépendances + durcissement de
     `loader._load_pdf` (ouverture/déchiffrement/pages englobés, PDF illisible ignoré).

2. **ChromaDB `KeyError: '_type'`**
   - Cause : `chroma_db/` résiduel écrit par une version différente de ChromaDB.
   - Correctif : reconstruction propre de la base (`rm -rf chroma_db` puis ingestion).

3. **Retrieval : codes d'erreur non remontés (ORA-01555 au rang 77)**
   - Cause : la recherche dense seule (BGE) ne fait pas ressortir un identifiant
     rare ; scores trop resserrés (0,56–0,63).
   - Correctif : retriever **hybride** — pool élargi + bonus lexical + garde-fou
     `ChromaDB $contains` sur le code exact. ORA-01555 remonte désormais au rang 1.

4. **Sécurité test** : `test_smoke.py` réinitialisait la collection de production.
   - Correctif : le test utilise désormais une base ChromaDB temporaire isolée.

## 6. Pipeline complet confirmé

```
Documents (PDF/TXT/LOG/MD)
  → Chunking (fenêtre glissante + overlap)
  → Embeddings (BAAI/bge-small-en-v1.5, normalisés)
  → ChromaDB (10 619 vecteurs, cosinus)
  → Retriever (dense + boost lexical / codes d'erreur)
  → Claude (claude-sonnet-4-6, prompt strict anti-hallucination)
  → Réponse + Sources (fichier, page, extrait exact)
```

✅ **Critère final atteint** : un utilisateur pose une question (AR/FR/EN) et
reçoit une réponse fondée sur les documents, avec les sources exactes.

## Notes

- La clé API est dans `backend/.env` (jamais en dur, fichier gitignoré).
- Validation menée sur le port **8001** car le port 8000 est occupé par un
  process tiers sur la machine. `frontend/.env` pointe donc vers `:8001`.
  Pour revenir au défaut, libérez le port 8000 et supprimez `frontend/.env`.
