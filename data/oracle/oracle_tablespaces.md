# Oracle — Tablespaces et fichiers de données

## Tablespaces

Un tablespace est une unité logique de stockage dans Oracle, composée d'un ou
plusieurs fichiers de données (datafiles). Les tablespaces principaux sont :

- `SYSTEM` : dictionnaire de données.
- `SYSAUX` : composants auxiliaires.
- `UNDO` : segments d'annulation (rollback).
- `TEMP` : opérations de tri temporaires.
- `USERS` : données applicatives par défaut.

## Créer un tablespace

```sql
CREATE TABLESPACE app_data
  DATAFILE '/u01/oradata/app_data01.dbf' SIZE 500M
  AUTOEXTEND ON NEXT 100M MAXSIZE 10G;
```

## Surveiller l'espace utilisé

```sql
SELECT tablespace_name,
       ROUND(used_space * 8192 / 1024 / 1024) AS used_mb,
       ROUND(tablespace_size * 8192 / 1024 / 1024) AS total_mb
FROM   dba_tablespace_usage_metrics;
```

## ORA-01653 : impossible d'étendre une table

L'erreur `ORA-01653: unable to extend table` signifie qu'un tablespace est plein.
Solutions :

1. Ajouter un fichier de données : `ALTER TABLESPACE app_data ADD DATAFILE '...' SIZE 1G;`
2. Activer l'auto-extension : `ALTER DATABASE DATAFILE '...' AUTOEXTEND ON;`
3. Augmenter la taille maximale : `ALTER DATABASE DATAFILE '...' AUTOEXTEND ON MAXSIZE UNLIMITED;`
