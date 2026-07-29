-- Keep recent match rows available for the menu and game rotation while
-- compacting old rows into one bounded aggregate per player/grid/mode/pace.
create table if not exists public.grid_player_history_rollups (
  user_id uuid not null references public.profiles(id) on delete cascade,
  grid_id text not null,
  mode text not null check (mode in ('solo', 'multiplayer')),
  pace text not null check (pace in ('realtime', 'async')),
  plays bigint not null default 0 check (plays >= 0),
  completions bigint not null default 0 check (completions >= 0),
  wins bigint not null default 0 check (wins >= 0),
  draws bigint not null default 0 check (draws >= 0),
  losses bigint not null default 0 check (losses >= 0),
  abandons bigint not null default 0 check (abandons >= 0),
  opponent_abandons bigint not null default 0 check (opponent_abandons >= 0),
  positive_reviews bigint not null default 0 check (positive_reviews >= 0),
  negative_reviews bigint not null default 0 check (negative_reviews >= 0),
  score_total bigint not null default 0 check (score_total >= 0),
  opponent_score_total bigint not null default 0 check (opponent_score_total >= 0),
  duration_seconds_sum bigint not null default 0 check (duration_seconds_sum >= 0),
  duration_samples bigint not null default 0 check (duration_samples >= 0),
  first_played_at timestamptz not null,
  last_played_at timestamptz not null,
  archived_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, grid_id, mode, pace)
);

create index if not exists grid_player_history_rollups_grid_idx
  on public.grid_player_history_rollups (grid_id, last_played_at desc);

alter table public.grid_player_history_rollups enable row level security;
revoke all on table public.grid_player_history_rollups from public, anon, authenticated;
grant select on table public.grid_player_history_rollups to service_role;

comment on table public.grid_player_history_rollups is
  'Bounded lifetime aggregates for detailed player history rows archived after the retention window.';

-- Popularity must remain stable when detailed rows move to the compact table.
create or replace function private.refresh_grid_popularity(p_grid_id text)
returns void
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $$
declare
  v_plays bigint;
  v_completions bigint;
  v_positive bigint;
  v_negative bigint;
  v_duration_sum bigint;
  v_duration_samples bigint;
  v_average_duration numeric(12,2);
  v_last_played timestamptz;
  v_rated bigint;
  v_satisfaction numeric;
  v_completion_rate numeric;
  v_confidence numeric;
  v_score numeric(6,2);
begin
  select
    coalesce(sum(source.plays), 0),
    coalesce(sum(source.completions), 0),
    coalesce(sum(source.positive_reviews), 0),
    coalesce(sum(source.negative_reviews), 0),
    coalesce(sum(source.duration_seconds_sum), 0),
    coalesce(sum(source.duration_samples), 0),
    max(source.last_played_at)
  into
    v_plays,
    v_completions,
    v_positive,
    v_negative,
    v_duration_sum,
    v_duration_samples,
    v_last_played
  from (
    select
      count(*)::bigint as plays,
      count(*) filter (where history.completed)::bigint as completions,
      count(*) filter (where history.feedback = 1)::bigint as positive_reviews,
      count(*) filter (where history.feedback = -1)::bigint as negative_reviews,
      coalesce(sum(history.duration_seconds), 0)::bigint as duration_seconds_sum,
      count(history.duration_seconds)::bigint as duration_samples,
      max(history.completed_at) as last_played_at
    from public.grid_player_history as history
    where history.grid_id = p_grid_id

    union all

    select
      coalesce(sum(rollup.plays), 0)::bigint,
      coalesce(sum(rollup.completions), 0)::bigint,
      coalesce(sum(rollup.positive_reviews), 0)::bigint,
      coalesce(sum(rollup.negative_reviews), 0)::bigint,
      coalesce(sum(rollup.duration_seconds_sum), 0)::bigint,
      coalesce(sum(rollup.duration_samples), 0)::bigint,
      max(rollup.last_played_at)
    from public.grid_player_history_rollups as rollup
    where rollup.grid_id = p_grid_id
  ) as source;

  if v_plays = 0 then
    delete from public.grid_popularity where grid_id = p_grid_id;
    return;
  end if;

  v_average_duration := case
    when v_duration_samples = 0 then null
    else round(v_duration_sum::numeric / v_duration_samples::numeric, 2)
  end;
  v_rated := v_positive + v_negative;
  v_satisfaction := (v_positive + 3.0) / (v_rated + 5.0);
  v_completion_rate := v_completions::numeric / greatest(v_plays, 1);
  v_confidence := least(1.0, v_rated::numeric / 20.0);
  v_score := round(100 * (
    0.70 * v_satisfaction
    + 0.20 * v_completion_rate
    + 0.10 * v_confidence
  ), 2);

  insert into public.grid_popularity (
    grid_id, plays, completions, positive_reviews, negative_reviews,
    average_duration_seconds, popularity_score, last_played_at, updated_at
  ) values (
    p_grid_id,
    least(v_plays, 2147483647)::integer,
    least(v_completions, 2147483647)::integer,
    least(v_positive, 2147483647)::integer,
    least(v_negative, 2147483647)::integer,
    v_average_duration,
    v_score,
    v_last_played,
    now()
  )
  on conflict (grid_id) do update set
    plays = excluded.plays,
    completions = excluded.completions,
    positive_reviews = excluded.positive_reviews,
    negative_reviews = excluded.negative_reviews,
    average_duration_seconds = excluded.average_duration_seconds,
    popularity_score = excluded.popularity_score,
    last_played_at = excluded.last_played_at,
    updated_at = excluded.updated_at;
end;
$$;

revoke all on function private.refresh_grid_popularity(text) from public, anon, authenticated;
grant execute on function private.refresh_grid_popularity(text) to service_role;

-- Suppress the expensive per-row popularity refresh only while the archival
-- transaction moves rows. The archival function refreshes each affected grid
-- exactly once after both statements have completed.
create or replace function private.refresh_grid_popularity_trigger()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $$
begin
  if current_setting('motman.history_archive_in_progress', true) = 'on' then
    return case when tg_op = 'DELETE' then old else new end;
  end if;

  if tg_op = 'DELETE' then
    perform private.refresh_grid_popularity(old.grid_id);
    return old;
  end if;

  perform private.refresh_grid_popularity(new.grid_id);
  if tg_op = 'UPDATE' and old.grid_id is distinct from new.grid_id then
    perform private.refresh_grid_popularity(old.grid_id);
  end if;
  return new;
end;
$$;

revoke all on function private.refresh_grid_popularity_trigger()
  from public, anon, authenticated;

drop trigger if exists refresh_grid_popularity_after_rollup
  on public.grid_player_history_rollups;
create trigger refresh_grid_popularity_after_rollup
after insert or update or delete on public.grid_player_history_rollups
for each row execute function private.refresh_grid_popularity_trigger();

create or replace function private.archive_old_grid_player_history(
  p_detail_retention_days integer default 90,
  p_unread_retention_days integer default 180,
  p_batch_size integer default 5000
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_history_ids uuid[] := '{}'::uuid[];
  v_grid_ids text[] := '{}'::text[];
  v_grid_id text;
  v_archived_rows integer := 0;
begin
  if p_detail_retention_days < 30 or p_detail_retention_days > 365 then
    raise exception 'detail retention must be between 30 and 365 days';
  end if;
  if p_unread_retention_days < p_detail_retention_days
    or p_unread_retention_days > 730
  then
    raise exception 'unread retention must be between detail retention and 730 days';
  end if;
  if p_batch_size < 1 or p_batch_size > 50000 then
    raise exception 'batch size must be between 1 and 50000';
  end if;

  if not pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended('motman-grid-player-history-archive', 0)
  ) then
    return pg_catalog.jsonb_build_object(
      'archivedRows', 0,
      'affectedGrids', 0,
      'skipped', true,
      'reason', 'already-running'
    );
  end if;

  select
    coalesce(pg_catalog.array_agg(candidate.id), '{}'::uuid[])
  into v_history_ids
  from (
    select history.id
    from public.grid_player_history as history
    where history.completed_at
        < pg_catalog.now() - pg_catalog.make_interval(days => p_detail_retention_days)
      and (
        history.pace <> 'async'
        or history.result_acknowledged_at is not null
        or history.completed_at
          < pg_catalog.now() - pg_catalog.make_interval(days => p_unread_retention_days)
      )
    order by history.completed_at, history.id
    limit p_batch_size
    for update skip locked
  ) as candidate;

  if pg_catalog.cardinality(v_history_ids) = 0 then
    return pg_catalog.jsonb_build_object(
      'archivedRows', 0,
      'affectedGrids', 0,
      'skipped', false
    );
  end if;

  select coalesce(pg_catalog.array_agg(distinct history.grid_id), '{}'::text[])
  into v_grid_ids
  from public.grid_player_history as history
  where history.id = any(v_history_ids);

  perform pg_catalog.set_config('motman.history_archive_in_progress', 'on', true);

  insert into public.grid_player_history_rollups (
    user_id,
    grid_id,
    mode,
    pace,
    plays,
    completions,
    wins,
    draws,
    losses,
    abandons,
    opponent_abandons,
    positive_reviews,
    negative_reviews,
    score_total,
    opponent_score_total,
    duration_seconds_sum,
    duration_samples,
    first_played_at,
    last_played_at,
    archived_at,
    updated_at
  )
  select
    history.user_id,
    history.grid_id,
    history.mode,
    history.pace,
    count(*)::bigint,
    count(*) filter (where history.completed)::bigint,
    count(*) filter (where history.outcome = 'win')::bigint,
    count(*) filter (where history.outcome = 'draw')::bigint,
    count(*) filter (where history.outcome = 'loss')::bigint,
    count(*) filter (where history.outcome = 'abandon')::bigint,
    count(*) filter (where history.outcome = 'opponent-abandoned')::bigint,
    count(*) filter (where history.feedback = 1)::bigint,
    count(*) filter (where history.feedback = -1)::bigint,
    coalesce(sum(history.score), 0)::bigint,
    coalesce(sum(history.opponent_score), 0)::bigint,
    coalesce(sum(history.duration_seconds), 0)::bigint,
    count(history.duration_seconds)::bigint,
    min(history.completed_at),
    max(history.completed_at),
    pg_catalog.now(),
    pg_catalog.now()
  from public.grid_player_history as history
  where history.id = any(v_history_ids)
  group by history.user_id, history.grid_id, history.mode, history.pace
  on conflict (user_id, grid_id, mode, pace) do update set
    plays = grid_player_history_rollups.plays + excluded.plays,
    completions = grid_player_history_rollups.completions + excluded.completions,
    wins = grid_player_history_rollups.wins + excluded.wins,
    draws = grid_player_history_rollups.draws + excluded.draws,
    losses = grid_player_history_rollups.losses + excluded.losses,
    abandons = grid_player_history_rollups.abandons + excluded.abandons,
    opponent_abandons =
      grid_player_history_rollups.opponent_abandons + excluded.opponent_abandons,
    positive_reviews =
      grid_player_history_rollups.positive_reviews + excluded.positive_reviews,
    negative_reviews =
      grid_player_history_rollups.negative_reviews + excluded.negative_reviews,
    score_total = grid_player_history_rollups.score_total + excluded.score_total,
    opponent_score_total =
      grid_player_history_rollups.opponent_score_total + excluded.opponent_score_total,
    duration_seconds_sum =
      grid_player_history_rollups.duration_seconds_sum + excluded.duration_seconds_sum,
    duration_samples =
      grid_player_history_rollups.duration_samples + excluded.duration_samples,
    first_played_at =
      least(grid_player_history_rollups.first_played_at, excluded.first_played_at),
    last_played_at =
      greatest(grid_player_history_rollups.last_played_at, excluded.last_played_at),
    archived_at = excluded.archived_at,
    updated_at = excluded.updated_at;

  delete from public.grid_player_history
  where id = any(v_history_ids);
  get diagnostics v_archived_rows = row_count;

  perform pg_catalog.set_config('motman.history_archive_in_progress', 'off', true);

  foreach v_grid_id in array v_grid_ids loop
    perform private.refresh_grid_popularity(v_grid_id);
  end loop;

  return pg_catalog.jsonb_build_object(
    'archivedRows', v_archived_rows,
    'affectedGrids', pg_catalog.cardinality(v_grid_ids),
    'skipped', false
  );
end;
$$;

revoke all on function private.archive_old_grid_player_history(integer, integer, integer)
  from public, anon, authenticated;

comment on function private.archive_old_grid_player_history(integer, integer, integer) is
  'Archives acknowledged history after 90 days and unread async results after at most 180 days, in bounded batches.';

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname = 'motman-archive-old-grid-history'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
end;
$$;

select cron.schedule(
  'motman-archive-old-grid-history',
  '37 3 * * *',
  'select private.archive_old_grid_player_history(90, 180, 5000);'
);
