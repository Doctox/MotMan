create table if not exists public.server_app_config (
  id text primary key check (id = 'motman'),
  revision integer not null check (revision > 0),
  android_version_name text not null check (android_version_name ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),
  android_version_code integer not null check (android_version_code > 0),
  updated_at timestamptz not null default now()
);

comment on table public.server_app_config is
  'Public, non-sensitive MotMan release metadata. Only server-side roles may write it.';

alter table public.server_app_config enable row level security;

revoke all on table public.server_app_config from anon, authenticated;
grant select on table public.server_app_config to anon, authenticated;

drop policy if exists "release metadata is publicly readable" on public.server_app_config;
create policy "release metadata is publicly readable"
  on public.server_app_config
  for select
  to anon, authenticated
  using (id = 'motman');

insert into public.server_app_config (
  id,
  revision,
  android_version_name,
  android_version_code
)
values ('motman', 47, '1.0.2', 3)
on conflict (id) do nothing;
