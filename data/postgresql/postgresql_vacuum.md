# PostgreSQL — VACUUM et maintenance

## VACUUM

La commande `VACUUM` récupère l'espace de stockage occupé par les lignes mortes
(dead tuples) créées par les opérations UPDATE et DELETE. Sans VACUUM, la table
grossit indéfiniment (phénomène de "table bloat").

- `VACUUM` simple : récupère l'espace mais ne le rend pas au système d'exploitation.
- `VACUUM FULL` : réécrit toute la table et rend l'espace au système, mais pose
  un verrou exclusif (ACCESS EXCLUSIVE LOCK) — à éviter en production aux heures de pointe.
- `VACUUM ANALYZE` : exécute VACUUM puis met à jour les statistiques du planificateur.

## Autovacuum

Le démon `autovacuum` exécute automatiquement VACUUM et ANALYZE en arrière-plan.
Paramètres importants dans postgresql.conf :

- `autovacuum = on`
- `autovacuum_vacuum_scale_factor = 0.2` (déclenche VACUUM quand 20% des lignes sont mortes)
- `autovacuum_naptime = 1min`

## Détecter le bloat

```sql
SELECT relname, n_dead_tup, n_live_tup
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

## Réindexation

`REINDEX INDEX nom_index;` reconstruit un index fragmenté. Utiliser
`REINDEX INDEX CONCURRENTLY` (PostgreSQL 12+) pour éviter de bloquer les écritures.
