-- Ranked matchmaking is deliberately separate from casual matchmaking:
-- one persistent queue, a 30-second two-player ready check, and an atomic
-- pause/resume/administrative-draw transition for realtime casual matches.

alter table public.player_progress
  add column if not exists ranked_matches integer not null default 0,
  add column if not exists ranked_wins integer not null default 0,
  add column if not exists ranked_losses integer not null default 0,
  add column if not exists ranked_draws integer not null default 0,
  add column if not exists ranked_peak_points integer not null default 0;

alter table public.player_progress
  drop constraint if exists player_progress_ranked_counts_check;
alter table public.player_progress
  add constraint player_progress_ranked_counts_check check (
    ranked_matches >= 0
    and ranked_wins >= 0
    and ranked_losses >= 0
    and ranked_draws >= 0
    and ranked_wins + ranked_losses + ranked_draws <= ranked_matches
    and ranked_peak_points >= 0
  );

alter table public.server_matches
  add column if not exists paused_at timestamptz,
  add column if not exists pause_reason text,
  add column if not exists paused_remaining_ms integer,
  add column if not exists ranked_ready_session_id uuid;

alter table public.server_matches
  drop constraint if exists server_matches_ranked_pause_check;
alter table public.server_matches
  add constraint server_matches_ranked_pause_check check (
    (
      paused_at is null
      and pause_reason is null
      and paused_remaining_ms is null
      and ranked_ready_session_id is null
    )
    or
    (
      paused_at is not null
      and pause_reason = 'ranked_ready'
      and paused_remaining_ms between 0 and 45000
      and ranked_ready_session_id is not null
      and status = 'active'
      and mode = 'normal'
      and pace = 'realtime'
    )
  );

create index if not exists server_matches_ranked_pause_idx
  on public.server_matches(ranked_ready_session_id)
  where ranked_ready_session_id is not null;

create table if not exists public.server_ranked_searches (
  user_id uuid primary key references auth.users(id) on delete cascade,
  status text not null default 'searching'
    check (status in ('searching', 'ready')),
  rating_snapshot integer not null,
  tier_snapshot integer not null check (tier_snapshot between 0 and 6),
  placement_snapshot integer not null default 0
    check (placement_snapshot between 0 and 5),
  claim_token uuid,
  claimed_by uuid references auth.users(id) on delete set null,
  claim_expires_at timestamptz,
  ready_session_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (
    (claim_token is null and claimed_by is null and claim_expires_at is null)
    or
    (claim_token is not null and claimed_by is not null and claim_expires_at is not null)
  )
);

alter table public.server_ranked_searches enable row level security;
revoke all on public.server_ranked_searches from public, anon, authenticated;
grant all on public.server_ranked_searches to service_role;

create index if not exists server_ranked_searches_queue_idx
  on public.server_ranked_searches(status, tier_snapshot, claim_expires_at, created_at, user_id);
create index if not exists server_ranked_searches_claimed_by_idx
  on public.server_ranked_searches(claimed_by)
  where claimed_by is not null;

create table if not exists public.server_ranked_ready_sessions (
  id uuid primary key default gen_random_uuid(),
  match_id uuid references public.server_matches(id) on delete set null,
  player_a_id uuid not null references auth.users(id) on delete cascade,
  player_b_id uuid not null references auth.users(id) on delete cascade,
  player_a_accepted boolean not null default false,
  player_b_accepted boolean not null default false,
  player_a_paused_match_id uuid references public.server_matches(id) on delete set null,
  player_b_paused_match_id uuid references public.server_matches(id) on delete set null,
  status text not null default 'pending'
    check (status in ('pending', 'started', 'cancelled', 'expired')),
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (player_a_id <> player_b_id)
);

alter table public.server_ranked_ready_sessions enable row level security;
revoke all on public.server_ranked_ready_sessions from public, anon, authenticated;
grant all on public.server_ranked_ready_sessions to service_role;

create index if not exists server_ranked_ready_player_a_idx
  on public.server_ranked_ready_sessions(player_a_id, status, expires_at);
create index if not exists server_ranked_ready_player_b_idx
  on public.server_ranked_ready_sessions(player_b_id, status, expires_at);
create unique index if not exists server_ranked_ready_pending_pair_idx
  on public.server_ranked_ready_sessions(
    least(player_a_id, player_b_id),
    greatest(player_a_id, player_b_id)
  )
  where status = 'pending';

alter table public.server_ranked_searches
  drop constraint if exists server_ranked_searches_ready_session_fk;
alter table public.server_ranked_searches
  add constraint server_ranked_searches_ready_session_fk
  foreign key (ready_session_id)
  references public.server_ranked_ready_sessions(id)
  on delete set null;

alter table public.server_matches
  drop constraint if exists server_matches_ranked_ready_session_fk;
alter table public.server_matches
  add constraint server_matches_ranked_ready_session_fk
  foreign key (ranked_ready_session_id)
  references public.server_ranked_ready_sessions(id)
  on delete set null
  deferrable initially deferred;

create table if not exists public.ranked_rating_events (
  match_id uuid not null references public.server_matches(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  opponent_id uuid not null references auth.users(id) on delete cascade,
  points_before integer not null,
  points_after integer not null,
  points_delta integer not null,
  expected_score numeric(8, 6) not null,
  actual_score numeric(2, 1) not null,
  placement_number integer not null check (placement_number between 0 and 5),
  created_at timestamptz not null default now(),
  primary key (match_id, user_id)
);

alter table public.ranked_rating_events enable row level security;
revoke all on public.ranked_rating_events from public, anon, authenticated;
grant all on public.ranked_rating_events to service_role;
create index if not exists ranked_rating_events_user_recent_idx
  on public.ranked_rating_events(user_id, created_at desc);

create or replace function private.ranked_effective_points(
  p_ranked_points integer,
  p_ranked_matches integer
)
returns integer
language sql
immutable
parallel safe
set search_path = ''
as $$
  select case
    when coalesce(p_ranked_matches, 0) = 0 then 1000
    else greatest(0, coalesce(p_ranked_points, 0))
  end;
$$;

create or replace function private.ranked_tier_index(p_points integer)
returns integer
language sql
immutable
parallel safe
set search_path = ''
as $$
  select case
    when coalesce(p_points, 0) < 1100 then 0
    when p_points < 1300 then 1
    when p_points < 1500 then 2
    when p_points < 1700 then 3
    when p_points < 1900 then 4
    when p_points < 2100 then 5
    else 6
  end;
$$;

create or replace function private.pause_realtime_normal_for_ranked(
  p_user_id uuid,
  p_ready_session_id uuid
)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  paused_match public.server_matches%rowtype;
  remaining_ms integer;
begin
  select match.*
  into paused_match
  from public.server_matches as match
  join public.match_participants as participant
    on participant.match_id = match.id
   and participant.user_id = p_user_id
  where match.status = 'active'
    and match.mode = 'normal'
    and match.pace = 'realtime'
    and match.paused_at is null
    and coalesce(match.state -> 'bot', 'null'::jsonb) = 'null'::jsonb
  order by match.updated_at desc, match.id
  for update of match skip locked
  limit 1;

  if not found then
    return null;
  end if;

  remaining_ms := greatest(
    0,
    least(
      45000,
      floor(
        extract(epoch from (
          paused_match.turn_ends_at - pg_catalog.clock_timestamp()
        )) * 1000
      )::integer
    )
  );

  update public.server_matches
  set paused_at = pg_catalog.clock_timestamp(),
      pause_reason = 'ranked_ready',
      paused_remaining_ms = remaining_ms,
      ranked_ready_session_id = p_ready_session_id,
      updated_at = pg_catalog.clock_timestamp()
  where id = paused_match.id;

  return paused_match.id;
end;
$$;

create or replace function private.resume_ranked_paused_match(
  p_match_id uuid,
  p_ready_session_id uuid
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
  resume_delay interval := interval '3 seconds';
begin
  if p_match_id is null then
    return;
  end if;

  update public.server_matches
  set turn_started_at = pg_catalog.clock_timestamp() + resume_delay,
      turn_ends_at = pg_catalog.clock_timestamp()
        + resume_delay
        + pg_catalog.make_interval(
          secs => greatest(0, coalesce(paused_remaining_ms, 0)) / 1000.0
        ),
      paused_at = null,
      pause_reason = null,
      paused_remaining_ms = null,
      ranked_ready_session_id = null,
      updated_at = pg_catalog.clock_timestamp()
  where id = p_match_id
    and status = 'active'
    and ranked_ready_session_id = p_ready_session_id;
end;
$$;

create or replace function private.finish_ranked_transfer_match(
  p_match_id uuid,
  p_ready_session_id uuid
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if p_match_id is null then
    return;
  end if;

  update public.server_matches
  set status = 'finished',
      current_player_id = null,
      winner_id = null,
      finish_reason = 'ranked_transfer',
      turn_started_at = pg_catalog.clock_timestamp(),
      turn_ends_at = pg_catalog.clock_timestamp(),
      paused_at = null,
      pause_reason = null,
      paused_remaining_ms = null,
      ranked_ready_session_id = null,
      updated_at = pg_catalog.clock_timestamp()
  where id = p_match_id
    and status = 'active'
    and ranked_ready_session_id = p_ready_session_id;
end;
$$;

create or replace function public.server_ranked_matchmake_atomic(
  p_user_id uuid,
  p_candidate_id uuid,
  p_claim_token uuid,
  p_grid_id text,
  p_state jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  own_progress public.player_progress%rowtype;
  candidate_search public.server_ranked_searches%rowtype;
  own_search public.server_ranked_searches%rowtype;
  created_match public.server_matches%rowtype;
  created_ready public.server_ranked_ready_sessions%rowtype;
  next_claim uuid;
  paused_a uuid;
  paused_b uuid;
  effective_points integer;
  effective_tier integer;
begin
  if p_user_id is null then
    return jsonb_build_object('status', 'invalid');
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('motman:ranked-matchmaking', 0)
  );

  if exists (
    select 1
    from public.server_matches as match
    join public.match_participants as participant
      on participant.match_id = match.id
     and participant.user_id = p_user_id
    where match.mode = 'ranked'
      and match.status in ('pending', 'active')
  ) then
    select search.*
    into own_search
    from public.server_ranked_searches as search
    where search.user_id = p_user_id;

    if found and own_search.ready_session_id is not null then
      return jsonb_build_object(
        'status', 'ready',
        'readySessionId', own_search.ready_session_id
      );
    end if;
    return jsonb_build_object('status', 'already-playing');
  end if;

  select progress.*
  into own_progress
  from public.player_progress as progress
  where progress.user_id = p_user_id
  for update;

  if not found then
    return jsonb_build_object('status', 'invalid');
  end if;

  effective_points := private.ranked_effective_points(
    own_progress.ranked_points,
    own_progress.ranked_matches
  );
  effective_tier := private.ranked_tier_index(effective_points);

  update public.server_ranked_searches
  set claim_token = null,
      claimed_by = null,
      claim_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where claim_expires_at <= pg_catalog.clock_timestamp()
    and status = 'searching';

  insert into public.server_ranked_searches(
    user_id,
    status,
    rating_snapshot,
    tier_snapshot,
    placement_snapshot,
    created_at,
    updated_at
  )
  values (
    p_user_id,
    'searching',
    effective_points,
    effective_tier,
    least(5, own_progress.ranked_matches),
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp()
  )
  on conflict (user_id) do update
  set rating_snapshot = excluded.rating_snapshot,
      tier_snapshot = excluded.tier_snapshot,
      placement_snapshot = excluded.placement_snapshot,
      updated_at = excluded.updated_at
  where public.server_ranked_searches.status = 'searching'
    and (
      public.server_ranked_searches.rating_snapshot,
      public.server_ranked_searches.tier_snapshot,
      public.server_ranked_searches.placement_snapshot
    ) is distinct from (
      excluded.rating_snapshot,
      excluded.tier_snapshot,
      excluded.placement_snapshot
    );

  if p_candidate_id is not null and p_claim_token is not null then
    select search.*
    into candidate_search
    from public.server_ranked_searches as search
    where search.user_id = p_candidate_id
      and search.status = 'searching'
      and search.claim_token = p_claim_token
      and search.claimed_by = p_user_id
      and search.claim_expires_at > pg_catalog.clock_timestamp()
    for update;

    select search.*
    into own_search
    from public.server_ranked_searches as search
    where search.user_id = p_user_id
      and search.status = 'searching'
      and search.claim_token = p_claim_token
      and search.claimed_by = p_user_id
      and search.claim_expires_at > pg_catalog.clock_timestamp()
    for update;

    if found and candidate_search.user_id is not null then
      if p_candidate_id = p_user_id
        or p_grid_id is null
        or p_state is null
        or p_state -> 'playerIds'
          is distinct from jsonb_build_array(p_candidate_id, p_user_id)
        or abs(candidate_search.tier_snapshot - own_search.tier_snapshot) > 1
        or not exists (
          select 1
          from public.server_grid_catalog as grid
          where grid.id = p_grid_id
            and grid.active is true
        )
        or exists (
          select 1
          from public.blocks as block
          where (block.owner_id = p_user_id and block.blocked_id = p_candidate_id)
             or (block.owner_id = p_candidate_id and block.blocked_id = p_user_id)
        )
      then
        update public.server_ranked_searches
        set claim_token = null,
            claimed_by = null,
            claim_expires_at = null,
            updated_at = pg_catalog.clock_timestamp()
        where user_id in (p_user_id, p_candidate_id);
        return jsonb_build_object('status', 'retry');
      end if;

      insert into public.server_matches(
        mode,
        pace,
        grid_id,
        state,
        status,
        current_player_id,
        turn_number,
        turn_started_at,
        turn_ends_at
      )
      values (
        'ranked',
        'realtime',
        p_grid_id,
        p_state,
        'pending',
        p_candidate_id,
        1,
        null,
        null
      )
      returning * into created_match;

      insert into public.match_participants(match_id, user_id, opponent_id)
      values
        (created_match.id, p_candidate_id, p_user_id),
        (created_match.id, p_user_id, p_candidate_id);

      insert into public.server_ranked_ready_sessions(
        match_id,
        player_a_id,
        player_b_id,
        expires_at
      )
      values (
        created_match.id,
        p_candidate_id,
        p_user_id,
        pg_catalog.clock_timestamp() + interval '30 seconds'
      )
      returning * into created_ready;

      paused_a := private.pause_realtime_normal_for_ranked(
        p_candidate_id,
        created_ready.id
      );
      paused_b := private.pause_realtime_normal_for_ranked(
        p_user_id,
        created_ready.id
      );

      update public.server_ranked_ready_sessions
      set player_a_paused_match_id = paused_a,
          player_b_paused_match_id = paused_b,
          updated_at = pg_catalog.clock_timestamp()
      where id = created_ready.id
      returning * into created_ready;

      update public.server_ranked_searches
      set status = 'ready',
          ready_session_id = created_ready.id,
          claim_token = null,
          claimed_by = null,
          claim_expires_at = null,
          updated_at = pg_catalog.clock_timestamp()
      where user_id in (p_user_id, p_candidate_id);

      return jsonb_build_object(
        'status', 'ready',
        'readySessionId', created_ready.id,
        'matchId', created_match.id,
        'opponentId', p_candidate_id,
        'created', true
      );
    end if;
  end if;

  select search.*
  into own_search
  from public.server_ranked_searches as search
  where search.user_id = p_user_id
  for update;

  if own_search.status = 'ready' and own_search.ready_session_id is not null then
    return jsonb_build_object(
      'status', 'ready',
      'readySessionId', own_search.ready_session_id
    );
  end if;

  if own_search.claim_token is not null
    and own_search.claim_expires_at > pg_catalog.clock_timestamp()
    and own_search.claimed_by <> p_user_id
  then
    return jsonb_build_object('status', 'waiting', 'claimed', true);
  end if;

  -- A casual match can only be suspended by one ready check at a time. If the
  -- caller is the opponent in somebody else's ready check, keep their ranked
  -- search alive but do not create a second overlapping transition.
  if exists (
    select 1
    from public.server_matches as paused_match
    join public.match_participants as paused_participant
      on paused_participant.match_id = paused_match.id
     and paused_participant.user_id = p_user_id
    where paused_match.status = 'active'
      and paused_match.paused_at is not null
      and paused_match.ranked_ready_session_id is not null
  ) then
    return jsonb_build_object('status', 'waiting', 'claimed', false);
  end if;

  select search.*
  into candidate_search
  from public.server_ranked_searches as search
  join public.profiles as profile
    on profile.id = search.user_id
   and profile.status = 'active'
  where search.status = 'searching'
    and search.user_id <> p_user_id
    and abs(search.tier_snapshot - own_search.tier_snapshot) <= 1
    and (
      search.claim_token is null
      or search.claim_expires_at <= pg_catalog.clock_timestamp()
    )
    and not exists (
      select 1
      from public.blocks as block
      where (block.owner_id = p_user_id and block.blocked_id = search.user_id)
         or (block.owner_id = search.user_id and block.blocked_id = p_user_id)
    )
    and not exists (
      select 1
      from public.server_matches as previous_match
      join public.match_participants as me
        on me.match_id = previous_match.id
       and me.user_id = p_user_id
      join public.match_participants as them
        on them.match_id = previous_match.id
       and them.user_id = search.user_id
      where previous_match.mode = 'ranked'
        and previous_match.status = 'finished'
        and previous_match.finish_reason in ('completed', 'timeout', 'forfeit')
        and previous_match.updated_at >
          pg_catalog.clock_timestamp() - interval '10 minutes'
    )
    and not exists (
      select 1
      from public.server_matches as active_ranked
      join public.match_participants as ranked_participant
        on ranked_participant.match_id = active_ranked.id
       and ranked_participant.user_id = search.user_id
      where active_ranked.mode = 'ranked'
        and active_ranked.status in ('pending', 'active')
    )
    and not exists (
      select 1
      from public.server_matches as paused_match
      join public.match_participants as paused_participant
        on paused_participant.match_id = paused_match.id
       and paused_participant.user_id = search.user_id
      where paused_match.status = 'active'
        and paused_match.paused_at is not null
        and paused_match.ranked_ready_session_id is not null
    )
  order by
    abs(search.rating_snapshot - own_search.rating_snapshot),
    search.created_at,
    search.user_id
  for update of search skip locked
  limit 1;

  if found then
    next_claim := pg_catalog.gen_random_uuid();
    update public.server_ranked_searches
    set claim_token = next_claim,
        claimed_by = p_user_id,
        claim_expires_at = pg_catalog.clock_timestamp() + interval '20 seconds',
        updated_at = pg_catalog.clock_timestamp()
    where user_id in (p_user_id, candidate_search.user_id);

    return jsonb_build_object(
      'status', 'candidate',
      'opponentId', candidate_search.user_id,
      'claimToken', next_claim
    );
  end if;

  return jsonb_build_object('status', 'waiting', 'claimed', false);
end;
$$;

create or replace function public.server_expire_ranked_ready_atomic(
  p_ready_session_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  ready public.server_ranked_ready_sessions%rowtype;
begin
  select session.*
  into ready
  from public.server_ranked_ready_sessions as session
  where session.id = p_ready_session_id
  for update;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;
  if ready.status <> 'pending' then
    return jsonb_build_object('status', ready.status);
  end if;
  if ready.expires_at > pg_catalog.clock_timestamp() then
    return jsonb_build_object('status', 'pending');
  end if;

  perform private.resume_ranked_paused_match(
    ready.player_a_paused_match_id,
    ready.id
  );
  perform private.resume_ranked_paused_match(
    ready.player_b_paused_match_id,
    ready.id
  );

  update public.server_matches
  set status = 'finished',
      current_player_id = null,
      winner_id = null,
      finish_reason = 'ready_expired',
      turn_started_at = pg_catalog.clock_timestamp(),
      turn_ends_at = pg_catalog.clock_timestamp(),
      updated_at = pg_catalog.clock_timestamp()
  where id = ready.match_id
    and status = 'pending';

  update public.server_ranked_ready_sessions
  set status = 'expired',
      updated_at = pg_catalog.clock_timestamp()
  where id = ready.id;

  if ready.player_a_accepted and not ready.player_b_accepted then
    update public.server_ranked_searches
    set status = 'searching',
        ready_session_id = null,
        claim_token = null,
        claimed_by = null,
        claim_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where user_id = ready.player_a_id;
    delete from public.server_ranked_searches
    where user_id = ready.player_b_id;
  elsif ready.player_b_accepted and not ready.player_a_accepted then
    update public.server_ranked_searches
    set status = 'searching',
        ready_session_id = null,
        claim_token = null,
        claimed_by = null,
        claim_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where user_id = ready.player_b_id;
    delete from public.server_ranked_searches
    where user_id = ready.player_a_id;
  else
    delete from public.server_ranked_searches
    where user_id in (ready.player_a_id, ready.player_b_id);
  end if;

  return jsonb_build_object('status', 'expired');
end;
$$;

create or replace function public.server_respond_ranked_ready_atomic(
  p_user_id uuid,
  p_ready_session_id uuid,
  p_decision text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  ready public.server_ranked_ready_sessions%rowtype;
  ranked_match public.server_matches%rowtype;
  opponent_id uuid;
begin
  if p_decision not in ('accept', 'decline') then
    return jsonb_build_object('status', 'invalid');
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'motman:ranked-ready:' || p_ready_session_id::text,
      0
    )
  );

  select session.*
  into ready
  from public.server_ranked_ready_sessions as session
  where session.id = p_ready_session_id
    and p_user_id in (session.player_a_id, session.player_b_id)
  for update;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;
  if ready.status = 'started' then
    return jsonb_build_object(
      'status', 'started',
      'matchId', ready.match_id
    );
  end if;
  if ready.status <> 'pending' then
    return jsonb_build_object('status', ready.status);
  end if;
  if ready.expires_at <= pg_catalog.clock_timestamp() then
    return public.server_expire_ranked_ready_atomic(ready.id);
  end if;

  opponent_id := case
    when p_user_id = ready.player_a_id then ready.player_b_id
    else ready.player_a_id
  end;

  if p_decision = 'decline' then
    perform private.resume_ranked_paused_match(
      ready.player_a_paused_match_id,
      ready.id
    );
    perform private.resume_ranked_paused_match(
      ready.player_b_paused_match_id,
      ready.id
    );

    update public.server_matches
    set status = 'finished',
        current_player_id = null,
        winner_id = null,
        finish_reason = 'ready_declined',
        turn_started_at = pg_catalog.clock_timestamp(),
        turn_ends_at = pg_catalog.clock_timestamp(),
        updated_at = pg_catalog.clock_timestamp()
    where id = ready.match_id
      and status = 'pending';

    update public.server_ranked_ready_sessions
    set status = 'cancelled',
        updated_at = pg_catalog.clock_timestamp()
    where id = ready.id;

    delete from public.server_ranked_searches
    where user_id = p_user_id;

    update public.server_ranked_searches
    set status = 'searching',
        ready_session_id = null,
        claim_token = null,
        claimed_by = null,
        claim_expires_at = null,
        updated_at = pg_catalog.clock_timestamp()
    where user_id = opponent_id;

    return jsonb_build_object(
      'status', 'declined',
      'opponentRequeued', true
    );
  end if;

  if p_user_id = ready.player_a_id then
    update public.server_ranked_ready_sessions
    set player_a_accepted = true,
        updated_at = pg_catalog.clock_timestamp()
    where id = ready.id
    returning * into ready;
  else
    update public.server_ranked_ready_sessions
    set player_b_accepted = true,
        updated_at = pg_catalog.clock_timestamp()
    where id = ready.id
    returning * into ready;
  end if;

  if not (ready.player_a_accepted and ready.player_b_accepted) then
    return jsonb_build_object(
      'status', 'accepted',
      'readySessionId', ready.id,
      'expiresAt', ready.expires_at
    );
  end if;

  update public.server_matches
  set status = 'active',
      turn_started_at = pg_catalog.clock_timestamp() + interval '1.8 seconds',
      turn_ends_at = pg_catalog.clock_timestamp() + interval '46.8 seconds',
      updated_at = pg_catalog.clock_timestamp()
  where id = ready.match_id
    and status = 'pending'
  returning * into ranked_match;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;

  perform private.finish_ranked_transfer_match(
    ready.player_a_paused_match_id,
    ready.id
  );
  if ready.player_b_paused_match_id is distinct from ready.player_a_paused_match_id then
    perform private.finish_ranked_transfer_match(
      ready.player_b_paused_match_id,
      ready.id
    );
  end if;

  update public.server_ranked_ready_sessions
  set status = 'started',
      updated_at = pg_catalog.clock_timestamp()
  where id = ready.id;

  delete from public.server_ranked_searches
  where user_id in (ready.player_a_id, ready.player_b_id);

  return jsonb_build_object(
    'status', 'started',
    'matchId', ranked_match.id,
    'match', to_jsonb(ranked_match),
    'closedNormalMatchIds', jsonb_build_array(
      ready.player_a_paused_match_id,
      ready.player_b_paused_match_id
    )
  );
end;
$$;

create or replace function public.server_apply_ranked_result_atomic(
  p_match_id uuid
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  ranked_match public.server_matches%rowtype;
  player_a uuid;
  player_b uuid;
  progress_a public.player_progress%rowtype;
  progress_b public.player_progress%rowtype;
  points_a integer;
  points_b integer;
  expected_a numeric;
  expected_b numeric;
  actual_a numeric;
  actual_b numeric;
  k_a integer;
  k_b integer;
  delta_a integer;
  delta_b integer;
  next_a integer;
  next_b integer;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'motman:ranked-result:' || p_match_id::text,
      0
    )
  );

  select match.*
  into ranked_match
  from public.server_matches as match
  where match.id = p_match_id
    and match.mode = 'ranked'
    and match.status = 'finished'
    and match.finish_reason in ('completed', 'timeout', 'forfeit')
  for update;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;

  if exists (
    select 1
    from public.ranked_rating_events as event
    where event.match_id = p_match_id
  ) then
    return jsonb_build_object('status', 'already-applied');
  end if;

  player_a := (ranked_match.state -> 'playerIds' ->> 0)::uuid;
  player_b := (ranked_match.state -> 'playerIds' ->> 1)::uuid;

  select progress.*
  into progress_a
  from public.player_progress as progress
  where progress.user_id = player_a
  for update;
  select progress.*
  into progress_b
  from public.player_progress as progress
  where progress.user_id = player_b
  for update;

  if progress_a.user_id is null or progress_b.user_id is null then
    return jsonb_build_object('status', 'invalid');
  end if;

  points_a := private.ranked_effective_points(
    progress_a.ranked_points,
    progress_a.ranked_matches
  );
  points_b := private.ranked_effective_points(
    progress_b.ranked_points,
    progress_b.ranked_matches
  );
  expected_a := 1.0 / (1.0 + power(10.0, (points_b - points_a) / 400.0));
  expected_b := 1.0 - expected_a;

  if ranked_match.winner_id is null then
    actual_a := 0.5;
    actual_b := 0.5;
  elsif ranked_match.winner_id = player_a then
    actual_a := 1.0;
    actual_b := 0.0;
  else
    actual_a := 0.0;
    actual_b := 1.0;
  end if;

  k_a := case when progress_a.ranked_matches < 5 then 64 else 40 end;
  k_b := case when progress_b.ranked_matches < 5 then 64 else 40 end;
  delta_a := round(k_a * (actual_a - expected_a));
  delta_b := round(k_b * (actual_b - expected_b));
  next_a := greatest(0, points_a + delta_a);
  next_b := greatest(0, points_b + delta_b);

  update public.player_progress
  set ranked_points = next_a,
      ranked_matches = ranked_matches + 1,
      ranked_wins = ranked_wins + case when actual_a = 1 then 1 else 0 end,
      ranked_losses = ranked_losses + case when actual_a = 0 then 1 else 0 end,
      ranked_draws = ranked_draws + case when actual_a = 0.5 then 1 else 0 end,
      ranked_peak_points = greatest(ranked_peak_points, next_a),
      updated_at = pg_catalog.clock_timestamp()
  where user_id = player_a;

  update public.player_progress
  set ranked_points = next_b,
      ranked_matches = ranked_matches + 1,
      ranked_wins = ranked_wins + case when actual_b = 1 then 1 else 0 end,
      ranked_losses = ranked_losses + case when actual_b = 0 then 1 else 0 end,
      ranked_draws = ranked_draws + case when actual_b = 0.5 then 1 else 0 end,
      ranked_peak_points = greatest(ranked_peak_points, next_b),
      updated_at = pg_catalog.clock_timestamp()
  where user_id = player_b;

  insert into public.ranked_rating_events(
    match_id,
    user_id,
    opponent_id,
    points_before,
    points_after,
    points_delta,
    expected_score,
    actual_score,
    placement_number
  )
  values
    (
      p_match_id,
      player_a,
      player_b,
      points_a,
      next_a,
      delta_a,
      expected_a,
      actual_a,
      least(5, progress_a.ranked_matches + 1)
    ),
    (
      p_match_id,
      player_b,
      player_a,
      points_b,
      next_b,
      delta_b,
      expected_b,
      actual_b,
      least(5, progress_b.ranked_matches + 1)
    );

  return jsonb_build_object(
    'status', 'applied',
    'playerA', jsonb_build_object(
      'userId', player_a,
      'pointsBefore', points_a,
      'pointsAfter', next_a,
      'delta', delta_a,
      'placements', least(5, progress_a.ranked_matches + 1)
    ),
    'playerB', jsonb_build_object(
      'userId', player_b,
      'pointsBefore', points_b,
      'pointsAfter', next_b,
      'delta', delta_b,
      'placements', least(5, progress_b.ranked_matches + 1)
    )
  );
end;
$$;

alter table public.grid_player_history
  drop constraint if exists grid_player_history_finish_reason_check;
alter table public.grid_player_history
  add constraint grid_player_history_finish_reason_check
  check (
    finish_reason is null
    or finish_reason in ('completed', 'timeout', 'forfeit', 'ranked_transfer')
  );

create or replace function private.broadcast_ranked_search_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.user_id, 'lobby');
  else
    perform private.broadcast_user_menu_wakeup(old.user_id, 'lobby');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_ranked_ready_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.player_a_id, 'lobby');
    perform private.broadcast_user_menu_wakeup(new.player_b_id, 'lobby');
  else
    perform private.broadcast_user_menu_wakeup(old.player_a_id, 'lobby');
    perform private.broadcast_user_menu_wakeup(old.player_b_id, 'lobby');
  end if;
  return null;
end;
$$;

drop trigger if exists ranked_searches_menu_wakeup
  on public.server_ranked_searches;
create trigger ranked_searches_menu_wakeup
after insert or update or delete on public.server_ranked_searches
for each row execute function private.broadcast_ranked_search_menu_wakeup();

drop trigger if exists ranked_ready_menu_wakeup
  on public.server_ranked_ready_sessions;
create trigger ranked_ready_menu_wakeup
after insert or update or delete on public.server_ranked_ready_sessions
for each row execute function private.broadcast_ranked_ready_menu_wakeup();

revoke all on function private.ranked_effective_points(integer, integer)
  from public, anon, authenticated;
revoke all on function private.ranked_tier_index(integer)
  from public, anon, authenticated;
revoke all on function private.pause_realtime_normal_for_ranked(uuid, uuid)
  from public, anon, authenticated;
revoke all on function private.resume_ranked_paused_match(uuid, uuid)
  from public, anon, authenticated;
revoke all on function private.finish_ranked_transfer_match(uuid, uuid)
  from public, anon, authenticated;
revoke all on function private.broadcast_ranked_search_menu_wakeup()
  from public, anon, authenticated;
revoke all on function private.broadcast_ranked_ready_menu_wakeup()
  from public, anon, authenticated;

revoke all on function public.server_ranked_matchmake_atomic(
  uuid, uuid, uuid, text, jsonb
) from public, anon, authenticated;
revoke all on function public.server_expire_ranked_ready_atomic(uuid)
  from public, anon, authenticated;
revoke all on function public.server_respond_ranked_ready_atomic(
  uuid, uuid, text
) from public, anon, authenticated;
revoke all on function public.server_apply_ranked_result_atomic(uuid)
  from public, anon, authenticated;

grant execute on function public.server_ranked_matchmake_atomic(
  uuid, uuid, uuid, text, jsonb
) to service_role;
grant execute on function public.server_expire_ranked_ready_atomic(uuid)
  to service_role;
grant execute on function public.server_respond_ranked_ready_atomic(
  uuid, uuid, text
) to service_role;
grant execute on function public.server_apply_ranked_result_atomic(uuid)
  to service_role;

comment on table public.server_ranked_searches is
  'Server-only persistent ranked queue. Same or adjacent tier only.';
comment on table public.server_ranked_ready_sessions is
  'Server-only 30-second two-player ready checks for ranked matches.';
comment on table public.ranked_rating_events is
  'Idempotent Elo-style ranked point changes, one event per player and match.';
