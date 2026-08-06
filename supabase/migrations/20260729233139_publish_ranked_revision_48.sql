-- Server-visible release marker for the first complete ranked-mode rollout.
-- The Android bundle itself remains 1.0.2 (versionCode 3) until the next AAB.

update public.server_app_config
set revision = 48,
    updated_at = pg_catalog.clock_timestamp()
where id = 'motman'
  and revision < 48;
