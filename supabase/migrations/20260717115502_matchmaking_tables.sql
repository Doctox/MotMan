
create table private.match_invitations (
  id uuid primary key default gen_random_uuid(),
  host_id uuid not null references auth.users(id) on delete cascade,
  guest_id uuid not null references auth.users(id) on delete cascade,
  pace text not null check (pace in ('realtime','async')),
  status text not null default 'pending' check (status in ('pending','accepted','declined','cancelled','expired')),
  match_id uuid references private.matches(id),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  check (host_id <> guest_id)
);
create index match_invitations_host on private.match_invitations(host_id, status);
create index match_invitations_guest on private.match_invitations(guest_id, status);

create table private.match_searches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  pace text not null check (pace in ('realtime','async')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id, pace)
);
create index match_searches_queue on private.match_searches(pace, created_at);

alter table public.match_participants add constraint match_participants_match_fk
  foreign key (match_id) references private.matches(id) on delete cascade;
alter table public.match_events add constraint match_events_match_fk
  foreign key (match_id) references private.matches(id) on delete cascade;
;
