begin;

do $$
declare
  player_a constant uuid := 'f0aa1001-0000-4000-8000-0000000000a1';
  player_b constant uuid := 'e0bb2002-0000-4000-8000-0000000000b2';
  casual_opponent constant uuid := 'd0cc3003-0000-4000-8000-0000000000c3';
  selected_grid text;
  casual_match_id uuid;
  ranked_match_id uuid;
  ready_id uuid;
  claim_token uuid;
  result jsonb;
begin
  insert into auth.users(id, is_anonymous, created_at, updated_at)
  values
    (player_a, false, pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()),
    (player_b, false, pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()),
    (casual_opponent, false, pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp());

  select grid.id
  into selected_grid
  from public.server_grid_catalog as grid
  where grid.active is true
  order by grid.id
  limit 1;

  if selected_grid is null then
    raise exception 'Ranked ready-check test requires one active grid';
  end if;

  insert into public.server_matches(
    mode, pace, grid_id, state, status, current_player_id, turn_number,
    turn_started_at, turn_ends_at
  )
  values (
    'normal',
    'realtime',
    selected_grid,
    pg_catalog.jsonb_build_object(
      'playerIds', pg_catalog.jsonb_build_array(player_a, casual_opponent),
      'bot', null,
      'scores', pg_catalog.jsonb_build_object(player_a::text, 0, casual_opponent::text, 0)
    ),
    'active',
    player_a,
    1,
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '45 seconds'
  )
  returning id into casual_match_id;

  insert into public.match_participants(match_id, user_id, opponent_id)
  values
    (casual_match_id, player_a, casual_opponent),
    (casual_match_id, casual_opponent, player_a);

  result := public.server_ranked_matchmake_atomic(
    player_a, null, null, null, null
  );
  if result ->> 'status' <> 'waiting' then
    raise exception 'First ranked player was not queued: %', result;
  end if;

  result := public.server_ranked_matchmake_atomic(
    player_b, null, null, null, null
  );
  if result ->> 'status' <> 'candidate'
    or result ->> 'opponentId' <> player_a::text
  then
    raise exception 'Second ranked player did not reserve the first: %', result;
  end if;

  claim_token := (result ->> 'claimToken')::uuid;
  result := public.server_ranked_matchmake_atomic(
    player_b,
    player_a,
    claim_token,
    selected_grid,
    pg_catalog.jsonb_build_object(
      'playerIds', pg_catalog.jsonb_build_array(player_a, player_b),
      'invitationId', null,
      'bot', null,
      'scores', pg_catalog.jsonb_build_object(player_a::text, 0, player_b::text, 0)
    )
  );

  if result ->> 'status' <> 'ready' then
    raise exception 'Ranked ready check was not created: %', result;
  end if;
  ready_id := (result ->> 'readySessionId')::uuid;
  ranked_match_id := (result ->> 'matchId')::uuid;

  if not exists (
    select 1
    from public.server_matches as match
    where match.id = casual_match_id
      and match.paused_at is not null
      and match.ranked_ready_session_id = ready_id
  ) then
    raise exception 'The realtime casual match was not paused atomically';
  end if;

  result := public.server_respond_ranked_ready_atomic(
    player_a, ready_id, 'accept'
  );
  if result ->> 'status' <> 'accepted' then
    raise exception 'First ranked acceptance failed: %', result;
  end if;

  result := public.server_respond_ranked_ready_atomic(
    player_b, ready_id, 'accept'
  );
  if result ->> 'status' <> 'started'
    or result ->> 'matchId' <> ranked_match_id::text
  then
    raise exception 'Second acceptance did not start the ranked match: %', result;
  end if;

  if not exists (
    select 1
    from public.server_matches as match
    where match.id = casual_match_id
      and match.status = 'finished'
      and match.finish_reason = 'ranked_transfer'
      and match.winner_id is null
  ) then
    raise exception 'The casual match did not close as an administrative draw';
  end if;

  update public.server_matches
  set status = 'finished',
      winner_id = player_a,
      finish_reason = 'completed',
      current_player_id = null,
      updated_at = pg_catalog.clock_timestamp()
  where id = ranked_match_id;

  result := public.server_apply_ranked_result_atomic(ranked_match_id);
  if result ->> 'status' <> 'applied' then
    raise exception 'Ranked rating was not applied: %', result;
  end if;

  if (
    select progress.ranked_points
    from public.player_progress as progress
    where progress.user_id = player_a
  ) <> 1032 then
    raise exception 'Unexpected winner placement rating';
  end if;
  if (
    select progress.ranked_points
    from public.player_progress as progress
    where progress.user_id = player_b
  ) <> 968 then
    raise exception 'Unexpected loser placement rating';
  end if;
  if (
    select count(*)
    from public.ranked_rating_events as event
    where event.match_id = ranked_match_id
  ) <> 2 then
    raise exception 'Expected one idempotent rating event per player';
  end if;

  result := public.server_apply_ranked_result_atomic(ranked_match_id);
  if result ->> 'status' <> 'already-applied' then
    raise exception 'Repeated ranked award was not idempotent: %', result;
  end if;

  if has_function_privilege(
    'authenticated',
    'public.server_ranked_matchmake_atomic(uuid,uuid,uuid,text,jsonb)',
    'EXECUTE'
  ) then
    raise exception 'Authenticated clients can execute the server-only ranked RPC';
  end if;
end;
$$;

rollback;
