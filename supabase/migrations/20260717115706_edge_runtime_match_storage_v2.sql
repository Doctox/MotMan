
create table public.server_grid_catalog (like private.grid_catalog including all);
insert into public.server_grid_catalog select * from private.grid_catalog on conflict (id) do nothing;
alter table public.server_grid_catalog enable row level security;
revoke all on public.server_grid_catalog from public, anon, authenticated;
grant select on public.server_grid_catalog to service_role;

create table public.server_matches (
  id uuid primary key default gen_random_uuid(),
  mode text not null check (mode in ('solo','friend','normal','ranked')),
  pace text not null check (pace in ('realtime','async')),
  grid_id text not null references public.server_grid_catalog(id),
  state jsonb not null,
  status text not null default 'active' check (status in ('pending','active','finished')),
  current_player_id uuid references auth.users(id),
  turn_number integer not null default 0,
  turn_started_at timestamptz,
  turn_ends_at timestamptz,
  winner_id uuid references auth.users(id),
  finish_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.server_matches enable row level security;
revoke all on public.server_matches from public, anon, authenticated;
grant all on public.server_matches to service_role;
create index server_matches_current_player on public.server_matches(current_player_id);
create index server_matches_grid on public.server_matches(grid_id);
create index server_matches_status on public.server_matches(status,updated_at);

create table public.server_match_invitations (
  id uuid primary key default gen_random_uuid(),
  host_id uuid not null references auth.users(id) on delete cascade,
  guest_id uuid not null references auth.users(id) on delete cascade,
  pace text not null check (pace in ('realtime','async')),
  status text not null default 'pending' check (status in ('pending','accepted','declined','cancelled','expired')),
  match_id uuid references public.server_matches(id),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  check (host_id <> guest_id)
);
alter table public.server_match_invitations enable row level security;
revoke all on public.server_match_invitations from public, anon, authenticated;
grant all on public.server_match_invitations to service_role;
create index server_invitations_host on public.server_match_invitations(host_id,status);
create index server_invitations_guest on public.server_match_invitations(guest_id,status);

create table public.server_match_searches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  pace text not null check (pace in ('realtime','async')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id,pace)
);
alter table public.server_match_searches enable row level security;
revoke all on public.server_match_searches from public, anon, authenticated;
grant all on public.server_match_searches to service_role;
create index server_searches_queue on public.server_match_searches(pace,created_at);

alter table public.match_participants drop constraint match_participants_match_fk;
alter table public.match_participants add constraint match_participants_match_fk foreign key(match_id) references public.server_matches(id) on delete cascade;
alter table public.match_events drop constraint match_events_match_fk;
alter table public.match_events add constraint match_events_match_fk foreign key(match_id) references public.server_matches(id) on delete cascade;
grant insert,update,delete on public.match_participants,public.match_events to service_role;
grant usage,select on sequence public.match_events_id_seq to service_role;
;
