-- Matchmaking used to select, create and clean up in separate Edge Function
-- requests. These short RPCs keep every irreversible transition in one
-- PostgreSQL transaction.

alter table public.server_match_searches
  add column if not exists claim_token uuid,
  add column if not exists claimed_by uuid references auth.users(id) on delete set null,
  add column if not exists claim_expires_at timestamptz;

alter table public.server_match_searches
  drop constraint if exists server_match_searches_claim_consistency;

alter table public.server_match_searches
  add constraint server_match_searches_claim_consistency check (
    (claim_token is null and claimed_by is null and claim_expires_at is null)
    or
    (claim_token is not null and claimed_by is not null and claim_expires_at is not null)
  );

create index if not exists server_searches_claimable
  on public.server_match_searches(pace, claim_expires_at, created_at, id);

create or replace function public.server_matchmake_atomic(
  p_user_id uuid,
  p_pace text,
  p_candidate_id uuid,
  p_claim_token uuid,
  p_grid_id text,
  p_state jsonb,
  p_turn_started_at timestamptz,
  p_turn_ends_at timestamptz
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  candidate_search public.server_match_searches%rowtype;
  own_search public.server_match_searches%rowtype;
  created_match public.server_matches%rowtype;
  next_claim_token uuid;
begin
  if p_user_id is null or p_pace not in ('realtime', 'async') then
    return jsonb_build_object('status', 'invalid');
  end if;

  -- A very short transaction-wide lock per pace makes discovery/reservation
  -- deterministic and avoids symmetric A->B / B->A queue races.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('motman:matchmaking:' || p_pace, 0)
  );

  update public.server_match_searches
  set claim_token = null,
      claimed_by = null,
      claim_expires_at = null,
      updated_at = pg_catalog.clock_timestamp()
  where pace = p_pace
    and claim_expires_at <= pg_catalog.clock_timestamp();

  if p_candidate_id is not null and p_claim_token is not null then
    select search.*
    into candidate_search
    from public.server_match_searches as search
    where search.user_id = p_candidate_id
      and search.pace = p_pace
      and search.claim_token = p_claim_token
      and search.claimed_by = p_user_id
      and search.claim_expires_at > pg_catalog.clock_timestamp()
    for update;

    if found then
      if p_candidate_id = p_user_id
        or p_grid_id is null
        or p_state is null
        or p_turn_started_at is null
        or p_turn_ends_at is null
        or p_turn_ends_at <= p_turn_started_at
        or p_state -> 'playerIds' is distinct from jsonb_build_array(p_candidate_id, p_user_id)
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
        or not exists (
          select 1
          from public.profiles as profile
          where profile.id = p_candidate_id
            and profile.status = 'active'
        )
      then
        update public.server_match_searches
        set claim_token = null,
            claimed_by = null,
            claim_expires_at = null,
            updated_at = pg_catalog.clock_timestamp()
        where id = candidate_search.id;
        return jsonb_build_object('status', 'retry');
      end if;

      insert into public.server_matches (
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
        'normal',
        p_pace,
        p_grid_id,
        p_state,
        'active',
        p_candidate_id,
        1,
        p_turn_started_at,
        p_turn_ends_at
      )
      returning * into created_match;

      insert into public.match_participants(match_id, user_id, opponent_id)
      values
        (created_match.id, p_candidate_id, p_user_id),
        (created_match.id, p_user_id, p_candidate_id);

      delete from public.server_match_searches
      where pace = p_pace
        and user_id in (p_user_id, p_candidate_id);

      return jsonb_build_object(
        'status', 'matched',
        'created', true,
        'matchId', created_match.id,
        'opponentId', p_candidate_id,
        'match', to_jsonb(created_match)
      );
    end if;
  end if;

  select search.*
  into own_search
  from public.server_match_searches as search
  where search.user_id = p_user_id
    and search.pace = p_pace
  for update;

  if found
    and own_search.claim_token is not null
    and own_search.claim_expires_at > pg_catalog.clock_timestamp()
    and own_search.claimed_by <> p_user_id
  then
    return jsonb_build_object('status', 'waiting', 'claimed', true);
  end if;

  select search.*
  into candidate_search
  from public.server_match_searches as search
  join public.profiles as profile on profile.id = search.user_id
  where search.pace = p_pace
    and search.user_id <> p_user_id
    and profile.status = 'active'
    and (search.claim_token is null or search.claim_expires_at <= pg_catalog.clock_timestamp())
    and not exists (
      select 1
      from public.blocks as block
      where (block.owner_id = p_user_id and block.blocked_id = search.user_id)
         or (block.owner_id = search.user_id and block.blocked_id = p_user_id)
    )
  order by search.created_at, search.id
  for update of search skip locked
  limit 1;

  if found then
    next_claim_token := pg_catalog.gen_random_uuid();
    update public.server_match_searches
    set claim_token = next_claim_token,
        claimed_by = p_user_id,
        claim_expires_at = pg_catalog.clock_timestamp() + interval '20 seconds',
        updated_at = pg_catalog.clock_timestamp()
    where id = candidate_search.id;

    delete from public.server_match_searches
    where user_id = p_user_id
      and pace = p_pace;

    return jsonb_build_object(
      'status', 'candidate',
      'opponentId', candidate_search.user_id,
      'claimToken', next_claim_token
    );
  end if;

  insert into public.server_match_searches (
    user_id,
    pace,
    claim_token,
    claimed_by,
    claim_expires_at,
    updated_at
  )
  values (p_user_id, p_pace, null, null, null, pg_catalog.clock_timestamp())
  on conflict (user_id, pace) do update
  set claim_token = null,
      claimed_by = null,
      claim_expires_at = null,
      updated_at = excluded.updated_at;

  return jsonb_build_object('status', 'waiting', 'claimed', false);
end;
$$;

create or replace function public.server_create_bot_match_atomic(
  p_user_id uuid,
  p_search_id uuid,
  p_grid_id text,
  p_state jsonb,
  p_turn_started_at timestamptz,
  p_turn_ends_at timestamptz
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  search_pace text;
  locked_search public.server_match_searches%rowtype;
  created_match public.server_matches%rowtype;
begin
  select search.pace
  into search_pace
  from public.server_match_searches as search
  where search.id = p_search_id
    and search.user_id = p_user_id;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('motman:matchmaking:' || search_pace, 0)
  );

  select search.*
  into locked_search
  from public.server_match_searches as search
  where search.id = p_search_id
    and search.user_id = p_user_id
  for update;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;

  if locked_search.created_at > pg_catalog.clock_timestamp() - interval '30 seconds'
    or (
      locked_search.claim_token is not null
      and locked_search.claim_expires_at > pg_catalog.clock_timestamp()
    )
  then
    return jsonb_build_object('status', 'waiting');
  end if;

  if p_grid_id is null
    or p_state is null
    or p_turn_started_at is null
    or p_turn_ends_at is null
    or p_turn_ends_at <= p_turn_started_at
    or p_state -> 'playerIds' ->> 0 is distinct from p_user_id::text
    or pg_catalog.jsonb_typeof(p_state -> 'bot') is distinct from 'object'
    or not exists (
      select 1
      from public.server_grid_catalog as grid
      where grid.id = p_grid_id
        and grid.active is true
    )
  then
    return jsonb_build_object('status', 'invalid');
  end if;

  insert into public.server_matches (
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
    'normal',
    locked_search.pace,
    p_grid_id,
    p_state,
    'active',
    p_user_id,
    1,
    p_turn_started_at,
    p_turn_ends_at
  )
  returning * into created_match;

  insert into public.match_participants(match_id, user_id, opponent_id)
  values (created_match.id, p_user_id, null);

  delete from public.server_match_searches
  where id = locked_search.id;

  return jsonb_build_object(
    'status', 'matched',
    'created', true,
    'matchId', created_match.id,
    'match', to_jsonb(created_match)
  );
end;
$$;

create or replace function public.server_respond_match_invitation_atomic(
  p_invitation_id uuid,
  p_guest_id uuid,
  p_decision text,
  p_grid_id text,
  p_state jsonb,
  p_turn_started_at timestamptz,
  p_turn_ends_at timestamptz
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  locked_invitation public.server_match_invitations%rowtype;
  existing_match public.server_matches%rowtype;
  created_match public.server_matches%rowtype;
begin
  if p_decision not in ('accept', 'decline') then
    return jsonb_build_object('status', 'invalid');
  end if;

  select invitation.*
  into locked_invitation
  from public.server_match_invitations as invitation
  where invitation.id = p_invitation_id
    and invitation.guest_id = p_guest_id
  for update;

  if not found then
    return jsonb_build_object('status', 'unavailable');
  end if;

  if locked_invitation.status = 'accepted' and locked_invitation.match_id is not null then
    select *
    into existing_match
    from public.server_matches
    where id = locked_invitation.match_id;

    return jsonb_build_object(
      'status', 'matched',
      'created', false,
      'matchId', locked_invitation.match_id,
      'match', to_jsonb(existing_match)
    );
  end if;

  if locked_invitation.status <> 'pending' then
    return jsonb_build_object('status', 'unavailable');
  end if;

  if locked_invitation.expires_at <= pg_catalog.clock_timestamp() then
    update public.server_match_invitations
    set status = 'expired'
    where id = locked_invitation.id;
    return jsonb_build_object('status', 'expired');
  end if;

  if p_decision = 'decline' then
    update public.server_match_invitations
    set status = 'declined'
    where id = locked_invitation.id;
    return jsonb_build_object('status', 'declined');
  end if;

  if p_grid_id is null
    or p_state is null
    or p_turn_started_at is null
    or p_turn_ends_at is null
    or p_turn_ends_at <= p_turn_started_at
    or p_state -> 'playerIds' is distinct from jsonb_build_array(locked_invitation.host_id, p_guest_id)
    or p_state ->> 'invitationId' is distinct from locked_invitation.id::text
    or not exists (
      select 1
      from public.server_grid_catalog as grid
      where grid.id = p_grid_id
        and grid.active is true
    )
    or not exists (
      select 1
      from public.friendships as friendship
      where friendship.left_user_id = least(locked_invitation.host_id, p_guest_id)
        and friendship.right_user_id = greatest(locked_invitation.host_id, p_guest_id)
    )
    or exists (
      select 1
      from public.blocks as block
      where (block.owner_id = locked_invitation.host_id and block.blocked_id = p_guest_id)
         or (block.owner_id = p_guest_id and block.blocked_id = locked_invitation.host_id)
    )
  then
    return jsonb_build_object('status', 'forbidden');
  end if;

  insert into public.server_matches (
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
    'friend',
    locked_invitation.pace,
    p_grid_id,
    p_state,
    'active',
    locked_invitation.host_id,
    1,
    p_turn_started_at,
    p_turn_ends_at
  )
  returning * into created_match;

  insert into public.match_participants(match_id, user_id, opponent_id)
  values
    (created_match.id, locked_invitation.host_id, p_guest_id),
    (created_match.id, p_guest_id, locked_invitation.host_id);

  update public.server_match_invitations
  set status = 'accepted',
      match_id = created_match.id
  where id = locked_invitation.id;

  delete from public.server_match_searches
  where user_id in (locked_invitation.host_id, p_guest_id);

  return jsonb_build_object(
    'status', 'matched',
    'created', true,
    'matchId', created_match.id,
    'match', to_jsonb(created_match)
  );
end;
$$;

revoke all on function public.server_matchmake_atomic(
  uuid, text, uuid, uuid, text, jsonb, timestamptz, timestamptz
) from public, anon, authenticated;
revoke all on function public.server_create_bot_match_atomic(
  uuid, uuid, text, jsonb, timestamptz, timestamptz
) from public, anon, authenticated;
revoke all on function public.server_respond_match_invitation_atomic(
  uuid, uuid, text, text, jsonb, timestamptz, timestamptz
) from public, anon, authenticated;

grant execute on function public.server_matchmake_atomic(
  uuid, text, uuid, uuid, text, jsonb, timestamptz, timestamptz
) to service_role;
grant execute on function public.server_create_bot_match_atomic(
  uuid, uuid, text, jsonb, timestamptz, timestamptz
) to service_role;
grant execute on function public.server_respond_match_invitation_atomic(
  uuid, uuid, text, text, jsonb, timestamptz, timestamptz
) to service_role;

comment on function public.server_matchmake_atomic(
  uuid, text, uuid, uuid, text, jsonb, timestamptz, timestamptz
) is 'Reserves a queued opponent and commits a human match atomically.';
comment on function public.server_create_bot_match_atomic(
  uuid, uuid, text, jsonb, timestamptz, timestamptz
) is 'Converts one stale search into a bot match atomically.';
comment on function public.server_respond_match_invitation_atomic(
  uuid, uuid, text, text, jsonb, timestamptz, timestamptz
) is 'Accepts or declines one invitation with row locking and idempotent acceptance.';
