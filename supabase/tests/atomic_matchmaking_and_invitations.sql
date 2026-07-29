begin;

do $$
declare
  first_user constant uuid := 'f0aa1001-0000-4000-8000-000000000001';
  second_user constant uuid := 'e0bb2002-0000-4000-8000-000000000002';
  selected_grid text;
  invitation_id uuid;
  reservation_token uuid;
  matchmaking_result jsonb;
  first_acceptance jsonb;
  repeated_acceptance jsonb;
begin
  insert into auth.users(id, is_anonymous, created_at, updated_at)
  values
    (first_user, false, pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()),
    (second_user, false, pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp());

  select grid.id
  into selected_grid
  from public.server_grid_catalog as grid
  where grid.active is true
  order by grid.id
  limit 1;

  if selected_grid is null then
    raise exception 'Atomic matchmaking test requires one active grid';
  end if;

  matchmaking_result := public.server_matchmake_atomic(
    first_user, 'realtime', null, null, null, null, null, null
  );
  if matchmaking_result ->> 'status' <> 'waiting' then
    raise exception 'First player was not queued: %', matchmaking_result;
  end if;

  matchmaking_result := public.server_matchmake_atomic(
    second_user, 'realtime', null, null, null, null, null, null
  );
  if matchmaking_result ->> 'status' <> 'candidate'
    or matchmaking_result ->> 'opponentId' <> first_user::text
  then
    raise exception 'Second player did not reserve the first: %', matchmaking_result;
  end if;

  reservation_token := (matchmaking_result ->> 'claimToken')::uuid;
  matchmaking_result := public.server_matchmake_atomic(
    second_user,
    'realtime',
    first_user,
    reservation_token,
    selected_grid,
    pg_catalog.jsonb_build_object(
      'playerIds', pg_catalog.jsonb_build_array(first_user, second_user),
      'invitationId', null,
      'bot', null
    ),
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '45 seconds'
  );
  if matchmaking_result ->> 'status' <> 'matched' then
    raise exception 'Reserved matchmaking commit failed: %', matchmaking_result;
  end if;

  if (
    select count(*)
    from public.server_matches as match
    where match.mode = 'normal'
      and match.state -> 'playerIds' = pg_catalog.jsonb_build_array(first_user, second_user)
  ) <> 1 then
    raise exception 'Matchmaking created an unexpected number of matches';
  end if;

  if (
    select count(*)
    from public.match_participants as participant
    where participant.match_id = (matchmaking_result ->> 'matchId')::uuid
  ) <> 2 then
    raise exception 'Matchmaking did not create both participants atomically';
  end if;

  perform public.server_matchmake_atomic(
    second_user,
    'realtime',
    first_user,
    reservation_token,
    selected_grid,
    pg_catalog.jsonb_build_object(
      'playerIds', pg_catalog.jsonb_build_array(first_user, second_user),
      'invitationId', null,
      'bot', null
    ),
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '45 seconds'
  );

  if (
    select count(*)
    from public.server_matches as match
    where match.mode = 'normal'
      and match.state -> 'playerIds' = pg_catalog.jsonb_build_array(first_user, second_user)
  ) <> 1 then
    raise exception 'A consumed reservation created a duplicate match';
  end if;

  insert into public.friendships(left_user_id, right_user_id)
  values (least(first_user, second_user), greatest(first_user, second_user));

  insert into public.server_match_invitations(host_id, guest_id, pace, expires_at)
  values (first_user, second_user, 'async', pg_catalog.clock_timestamp() + interval '1 day')
  returning id into invitation_id;

  first_acceptance := public.server_respond_match_invitation_atomic(
    invitation_id,
    second_user,
    'accept',
    selected_grid,
    pg_catalog.jsonb_build_object(
      'playerIds', pg_catalog.jsonb_build_array(first_user, second_user),
      'invitationId', invitation_id,
      'bot', null
    ),
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '1 day'
  );
  repeated_acceptance := public.server_respond_match_invitation_atomic(
    invitation_id,
    second_user,
    'accept',
    selected_grid,
    pg_catalog.jsonb_build_object(
      'playerIds', pg_catalog.jsonb_build_array(first_user, second_user),
      'invitationId', invitation_id,
      'bot', null
    ),
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '1 day'
  );

  if first_acceptance ->> 'status' <> 'matched'
    or first_acceptance ->> 'created' <> 'true'
    or repeated_acceptance ->> 'status' <> 'matched'
    or repeated_acceptance ->> 'created' <> 'false'
    or first_acceptance ->> 'matchId' is distinct from repeated_acceptance ->> 'matchId'
  then
    raise exception 'Invitation acceptance is not idempotent: first=%, repeated=%',
      first_acceptance, repeated_acceptance;
  end if;

  if (
    select count(*)
    from public.server_matches as match
    where match.mode = 'friend'
      and match.state ->> 'invitationId' = invitation_id::text
  ) <> 1 then
    raise exception 'Invitation acceptance created a duplicate match';
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'public.server_matchmake_atomic(uuid,text,uuid,uuid,text,jsonb,timestamptz,timestamptz)',
    'execute'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    'public.server_respond_match_invitation_atomic(uuid,uuid,text,text,jsonb,timestamptz,timestamptz)',
    'execute'
  ) then
    raise exception 'Atomic match RPCs must remain service-role only';
  end if;
end;
$$;

rollback;
