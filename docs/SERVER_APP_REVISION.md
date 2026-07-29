# Révision MotMan pilotée par Supabase

L’AAB conserve sa vraie version Android (`versionName` et `versionCode`).
Le numéro court affiché dans les paramètres (`#47`, `#48`, etc.) vient de
`public.server_app_config`.

Le client relit cette ligne à chaque ouverture des paramètres et conserve la
dernière valeur valide pour rester lisible hors ligne. Les rôles `anon` et
`authenticated` peuvent uniquement lire cette métadonnée ; aucune écriture
n’est autorisée depuis l’application.

Pour publier une nouvelle révision interne sans refaire l’AAB :

```sql
update public.server_app_config
set revision = 48,
    updated_at = now()
where id = 'motman';
```

Lorsqu’un nouvel AAB est réellement publié, mettre aussi à jour les métadonnées
Android :

```sql
update public.server_app_config
set revision = 49,
    android_version_name = '1.0.3',
    android_version_code = 4,
    updated_at = now()
where id = 'motman';
```
