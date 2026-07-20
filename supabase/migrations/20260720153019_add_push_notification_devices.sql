create table public.push_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  token text not null unique,
  platform text not null check (platform in ('android', 'ios')),
  app_id text not null default 'com.motman.game',
  enabled boolean not null default true,
  last_seen_at timestamptz not null default now(),
  last_notified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint push_devices_token_length check (char_length(token) between 20 and 4096),
  constraint push_devices_app_id_length check (char_length(app_id) between 3 and 160)
);

alter table public.push_devices enable row level security;
revoke all on public.push_devices from public, anon, authenticated;
grant all on public.push_devices to service_role;

create index push_devices_user_enabled_idx
  on public.push_devices (user_id, last_seen_at desc)
  where enabled is true;

comment on table public.push_devices is
  'Server-only FCM/APNS registration tokens for MotMan turn and invitation notifications.';
