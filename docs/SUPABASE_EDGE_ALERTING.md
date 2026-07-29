# Alertes Supabase Edge de MotMan

MotMan surveille ses Edge Functions toutes les cinq minutes avec GitHub Actions. La surveillance interroge directement les journaux `function_edge_logs` de Supabase : elle n’ajoute donc aucune écriture à la base et aucun travail aux requêtes des joueurs.

## Seuils par défaut

La fenêtre analysée couvre les quinze dernières minutes :

- au moins une réponse HTTP `5xx` ouvre une alerte critique ;
- au moins cinq réponses HTTP `429` ouvrent une alerte ;
- une latence p95 supérieure à 1 500 ms ouvre une alerte à partir de vingt invocations ;
- plus de 1 000 invocations Edge ouvre une alerte de volume.

Une seule issue GitHub `[MotMan] Alerte Supabase Edge Functions` est conservée. Elle est mise à jour tant que le problème persiste puis fermée automatiquement au retour à la normale. Une panne de la surveillance elle-même ouvre une issue distincte.

## Configuration GitHub

Le workflow est `.github/workflows/monitor-supabase-edge.yml`.

Secret obligatoire :

- `SUPABASE_ACCESS_TOKEN` : jeton Supabase capable de lire les analytics/logs. Un jeton finement limité à `analytics_logs_read` est préférable.

Variables :

- `SUPABASE_PROJECT_REF=kfacjvxzdtxybvxhfmzg`
- `EDGE_ALERT_WINDOW_MINUTES=15`
- `EDGE_ALERT_MAX_5XX=0`
- `EDGE_ALERT_MAX_429=4`
- `EDGE_ALERT_MAX_P95_MS=1500`
- `EDGE_ALERT_MAX_INVOCATIONS=1000`
- `EDGE_ALERT_MIN_INVOCATIONS_FOR_LATENCY=20`

Ces valeurs peuvent être changées dans GitHub, sans modifier ni republier l’application.

## Test manuel

Le workflow peut être lancé depuis GitHub : **Actions → Monitor Supabase Edge Functions → Run workflow**.

En local :

```powershell
$env:SUPABASE_ACCESS_TOKEN = '...'
$env:SUPABASE_PROJECT_REF = 'kfacjvxzdtxybvxhfmzg'
node scripts/check_supabase_edge_alerts.mjs
```

Le dernier rapport JSON est écrit dans `output/monitoring/supabase-edge-health.json`. Ce dossier est ignoré par Git.

## Coût et sécurité

Cette solution utilise l’API de logs Supabase à une cadence très inférieure à sa limite officielle de 30 requêtes par minute. Elle évite l’option Log Drains, facturée séparément. Le jeton Supabase reste dans les secrets chiffrés de GitHub et n’est jamais intégré au client web ou Android.
