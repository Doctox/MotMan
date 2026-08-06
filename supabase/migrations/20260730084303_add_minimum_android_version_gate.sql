alter table public.server_app_config
  add column if not exists minimum_android_version_code integer,
  add column if not exists android_store_url text;

update public.server_app_config
set minimum_android_version_code = coalesce(minimum_android_version_code, 3),
    android_store_url = coalesce(
      nullif(android_store_url, ''),
      'https://play.google.com/store/apps/details?id=com.motman.game'
    ),
    android_version_name = '1.0.3',
    android_version_code = 4,
    revision = greatest(revision, 49),
    updated_at = pg_catalog.clock_timestamp()
where id = 'motman';

alter table public.server_app_config
  alter column minimum_android_version_code set default 3,
  alter column minimum_android_version_code set not null,
  alter column android_store_url set default 'https://play.google.com/store/apps/details?id=com.motman.game',
  alter column android_store_url set not null;

alter table public.server_app_config
  drop constraint if exists server_app_config_android_version_range,
  add constraint server_app_config_android_version_range
    check (
      minimum_android_version_code > 0
      and minimum_android_version_code <= android_version_code
    ),
  drop constraint if exists server_app_config_android_store_url,
  add constraint server_app_config_android_store_url
    check (
      android_store_url = 'https://play.google.com/store/apps/details?id=com.motman.game'
    );

comment on column public.server_app_config.minimum_android_version_code is
  'Minimum Android versionCode allowed for online services. Keep at 3 until AAB versionCode 4 is available in Google Play.';

comment on column public.server_app_config.android_store_url is
  'Public Google Play URL displayed by the mandatory update screen.';
