
create extension if not exists pgcrypto;
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  friend_code text not null unique,
  avatar_id text not null default 'plume-motman',
  frame_id text not null default 'cadre-ivoire',
  animation_id text not null default 'animation-none',
  account_kind text not null default 'guest' check (account_kind in ('guest','account')),
  role text not null default 'player' check (role in ('player','moderator','admin')),
  status text not null default 'active' check (status in ('active','suspended','banned')),
  activity text not null default 'online' check (activity in ('online','playing')),
  last_seen timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_display_name_length check (char_length(display_name) between 3 and 16),
  constraint profiles_friend_code_format check (friend_code ~ '^[A-F0-9]{8}$')
);
create unique index profiles_display_name_unique on public.profiles (lower(display_name));

create table public.player_progress (
  user_id uuid primary key references auth.users(id) on delete cascade,
  level integer not null default 1 check (level between 1 and 50),
  xp integer not null default 0 check (xp >= 0),
  lifetime_xp integer not null default 0 check (lifetime_xp >= 0),
  ranked_points integer not null default 0,
  wins integer not null default 0 check (wins >= 0),
  losses integer not null default 0 check (losses >= 0),
  updated_at timestamptz not null default now()
);

create table public.player_wallets (
  user_id uuid primary key references auth.users(id) on delete cascade,
  feathers bigint not null default 600 check (feathers >= 0),
  basket_pity integer not null default 0 check (basket_pity between 0 and 20),
  opened_baskets integer not null default 0 check (opened_baskets >= 0),
  updated_at timestamptz not null default now()
);

create table public.player_inventory (
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('avatar','frame','animation')),
  item_id text not null,
  acquired_at timestamptz not null default now(),
  source text not null,
  primary key (user_id, kind, item_id)
);

create table public.economy_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  idempotency_key text not null,
  kind text not null,
  amount bigint not null,
  balance_after bigint not null check (balance_after >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);

create table public.experience_awards (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  idempotency_key text not null,
  mode text not null check (mode in ('solo','multiplayer')),
  outcome text not null check (outcome in ('win','draw','loss','abandon','opponent-abandoned')),
  productive_turns integer not null default 0 check (productive_turns >= 0),
  xp_amount integer not null check (xp_amount >= 0),
  feather_amount integer not null check (feather_amount >= 0),
  level_before integer not null,
  level_after integer not null,
  created_at timestamptz not null default now(),
  unique (user_id, idempotency_key)
);

create table public.friend_requests (
  id uuid primary key default gen_random_uuid(),
  from_user_id uuid not null references auth.users(id) on delete cascade,
  to_user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (from_user_id, to_user_id),
  check (from_user_id <> to_user_id)
);

create table public.friendships (
  left_user_id uuid not null references auth.users(id) on delete cascade,
  right_user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (left_user_id, right_user_id),
  check (left_user_id < right_user_id)
);

create table public.blocks (
  owner_id uuid not null references auth.users(id) on delete cascade,
  blocked_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (owner_id, blocked_id),
  check (owner_id <> blocked_id)
);

create table public.reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references auth.users(id) on delete cascade,
  reported_id uuid not null references auth.users(id) on delete cascade,
  reason text not null check (reason in ('pseudo','comportement','triche','harcelement','autre')),
  details text not null default '' check (char_length(details) <= 500),
  match_id uuid,
  status text not null default 'open' check (status in ('open','reviewed','dismissed','actioned')),
  created_at timestamptz not null default now(),
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id),
  check (reporter_id <> reported_id)
);

create table private.grid_catalog (
  id text primary key,
  version integer not null,
  columns integer not null,
  rows integer not null,
  payload jsonb not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table private.matches (
  id uuid primary key default gen_random_uuid(),
  mode text not null check (mode in ('solo','friend','normal','ranked')),
  pace text not null check (pace in ('realtime','async')),
  grid_id text not null references private.grid_catalog(id),
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

create table public.match_participants (
  match_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  opponent_id uuid references auth.users(id),
  score integer not null default 0 check (score >= 0),
  inactivity_count integer not null default 0 check (inactivity_count between 0 and 3),
  joined_at timestamptz not null default now(),
  primary key (match_id, user_id)
);

create table public.match_events (
  id bigint generated always as identity primary key,
  match_id uuid not null,
  recipient_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index match_events_recipient on public.match_events(recipient_id, id);
create index friend_requests_to on public.friend_requests(to_user_id, created_at);
create index reports_status on public.reports(status, created_at);
create index economy_transactions_user on public.economy_transactions(user_id, created_at);

alter table public.profiles enable row level security;
alter table public.player_progress enable row level security;
alter table public.player_wallets enable row level security;
alter table public.player_inventory enable row level security;
alter table public.economy_transactions enable row level security;
alter table public.experience_awards enable row level security;
alter table public.friend_requests enable row level security;
alter table public.friendships enable row level security;
alter table public.blocks enable row level security;
alter table public.reports enable row level security;
alter table public.match_participants enable row level security;
alter table public.match_events enable row level security;

create policy profiles_read_authenticated on public.profiles for select to authenticated using (true);
create policy profiles_update_self on public.profiles for update to authenticated
  using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

create policy progress_read_self on public.player_progress for select to authenticated using ((select auth.uid()) = user_id);
create policy wallets_read_self on public.player_wallets for select to authenticated using ((select auth.uid()) = user_id);
create policy inventory_read_self on public.player_inventory for select to authenticated using ((select auth.uid()) = user_id);
create policy transactions_read_self on public.economy_transactions for select to authenticated using ((select auth.uid()) = user_id);
create policy awards_read_self on public.experience_awards for select to authenticated using ((select auth.uid()) = user_id);

create policy friend_requests_read_participant on public.friend_requests for select to authenticated
  using ((select auth.uid()) in (from_user_id, to_user_id));
create policy friend_requests_insert_self on public.friend_requests for insert to authenticated
  with check ((select auth.uid()) = from_user_id);
create policy friend_requests_delete_participant on public.friend_requests for delete to authenticated
  using ((select auth.uid()) in (from_user_id, to_user_id));

create policy friendships_read_participant on public.friendships for select to authenticated
  using ((select auth.uid()) in (left_user_id, right_user_id));
create policy blocks_manage_self on public.blocks for all to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy reports_insert_self on public.reports for insert to authenticated
  with check ((select auth.uid()) = reporter_id);
create policy reports_read_self on public.reports for select to authenticated
  using ((select auth.uid()) = reporter_id);
create policy match_participants_read_self on public.match_participants for select to authenticated
  using ((select auth.uid()) = user_id);
create policy match_events_read_self on public.match_events for select to authenticated
  using ((select auth.uid()) = recipient_id);

grant usage on schema public to anon, authenticated;
grant select on public.profiles to authenticated;
grant update(display_name, avatar_id, frame_id, animation_id, activity, last_seen, updated_at) on public.profiles to authenticated;
grant select on public.player_progress, public.player_wallets, public.player_inventory, public.economy_transactions,
  public.experience_awards, public.friendships, public.match_participants, public.match_events to authenticated;
grant select, insert, delete on public.friend_requests to authenticated;
grant select, insert, delete on public.blocks to authenticated;
grant select, insert on public.reports to authenticated;

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  suffix text := upper(substr(replace(new.id::text, '-', ''), 1, 8));
begin
  insert into public.profiles(id, display_name, friend_code, account_kind)
  values (new.id, 'Invité ' || substr(suffix, 1, 4), suffix, case when new.is_anonymous then 'guest' else 'account' end);
  insert into public.player_progress(user_id) values (new.id);
  insert into public.player_wallets(user_id) values (new.id);
  insert into public.player_inventory(user_id, kind, item_id, source) values
    (new.id, 'avatar', 'plume-motman', 'starter'),
    (new.id, 'frame', 'cadre-ivoire', 'starter'),
    (new.id, 'animation', 'animation-none', 'starter');
  return new;
end;
$$;
revoke all on function private.handle_new_user() from public, anon, authenticated;

create trigger on_auth_user_created
after insert on auth.users
for each row execute function private.handle_new_user();

alter publication supabase_realtime add table public.match_events;
;
