begin;

do $$
declare
  test_user constant uuid := 'f0aa1001-0000-4000-8000-000000000091';
  selected_grid text;
  result jsonb;
  popularity_before jsonb;
  popularity_after jsonb;
begin
  insert into auth.users(id, is_anonymous, created_at, updated_at)
  values (test_user, false, pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp());

  select grid.id
  into selected_grid
  from public.server_grid_catalog as grid
  where grid.active is true
  order by grid.id
  limit 1;

  if selected_grid is null then
    raise exception 'History retention test requires one active grid';
  end if;

  insert into public.grid_player_history (
    user_id, play_key, grid_id, mode, pace, outcome, completed,
    score, opponent_score, duration_seconds, feedback, completed_at,
    finish_reason, result_acknowledged_at
  ) values
    (
      test_user, 'retention:acknowledged', selected_grid, 'multiplayer',
      'async', 'win', true, 8, 5, 120, 1,
      pg_catalog.now() - interval '91 days', 'completed',
      pg_catalog.now() - interval '91 days'
    ),
    (
      test_user, 'retention:unread-kept', selected_grid, 'multiplayer',
      'async', 'loss', true, 4, 9, 150, -1,
      pg_catalog.now() - interval '91 days', 'completed', null
    ),
    (
      test_user, 'retention:unread-expired', selected_grid, 'multiplayer',
      'async', 'draw', true, 7, 7, 90, null,
      pg_catalog.now() - interval '181 days', 'completed', null
    ),
    (
      test_user, 'retention:recent', selected_grid, 'solo',
      'realtime', 'win', true, 10, 3, 60, 1,
      pg_catalog.now() - interval '1 day', 'completed',
      pg_catalog.now() - interval '1 day'
    );

  select pg_catalog.jsonb_build_object(
    'plays', popularity.plays,
    'completions', popularity.completions,
    'positive', popularity.positive_reviews,
    'negative', popularity.negative_reviews,
    'duration', popularity.average_duration_seconds
  )
  into popularity_before
  from public.grid_popularity as popularity
  where popularity.grid_id = selected_grid;

  result := private.archive_old_grid_player_history(90, 180, 5000);

  if (result ->> 'archivedRows')::integer <> 2 then
    raise exception 'Expected two archived rows, got %', result;
  end if;

  if (
    select count(*)
    from public.grid_player_history
    where user_id = test_user
  ) <> 2 then
    raise exception 'Recent or unread detail retention is incorrect';
  end if;

  if not exists (
    select 1
    from public.grid_player_history
    where user_id = test_user and play_key = 'retention:unread-kept'
  ) then
    raise exception 'An unread 91-day async result was archived too early';
  end if;

  if (
    select coalesce(sum(plays), 0)
    from public.grid_player_history_rollups
    where user_id = test_user and grid_id = selected_grid
  ) <> 2 then
    raise exception 'The compact rollup did not receive both old rows';
  end if;

  if (
    select coalesce(sum(draws), 0)
    from public.grid_player_history_rollups
    where user_id = test_user and grid_id = selected_grid
  ) <> 1 then
    raise exception 'Outcome counters were not preserved in the rollup';
  end if;

  select pg_catalog.jsonb_build_object(
    'plays', popularity.plays,
    'completions', popularity.completions,
    'positive', popularity.positive_reviews,
    'negative', popularity.negative_reviews,
    'duration', popularity.average_duration_seconds
  )
  into popularity_after
  from public.grid_popularity as popularity
  where popularity.grid_id = selected_grid;

  if popularity_after is distinct from popularity_before then
    raise exception 'Popularity changed during archival: before=%, after=%',
      popularity_before, popularity_after;
  end if;

  result := private.archive_old_grid_player_history(90, 180, 5000);
  if (result ->> 'archivedRows')::integer <> 0 then
    raise exception 'A second archive pass was not idempotent: %', result;
  end if;

  if pg_catalog.has_function_privilege(
    'anon',
    'private.archive_old_grid_player_history(integer,integer,integer)',
    'execute'
  ) or pg_catalog.has_function_privilege(
    'authenticated',
    'private.archive_old_grid_player_history(integer,integer,integer)',
    'execute'
  ) then
    raise exception 'History archival function must not be client-callable';
  end if;
end;
$$;

rollback;
