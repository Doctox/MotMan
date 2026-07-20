-- Server-owned content telemetry. Player clients can only reach these tables
-- through authenticated Edge Functions; no Data API access is granted.
create table if not exists public.grid_player_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  play_key text not null,
  match_id uuid references public.server_matches(id) on delete set null,
  grid_id text not null,
  mode text not null check (mode in ('solo', 'multiplayer')),
  pace text not null check (pace in ('realtime', 'async')),
  outcome text not null check (outcome in ('win', 'draw', 'loss', 'abandon', 'opponent-abandoned')),
  completed boolean not null default false,
  score integer not null default 0 check (score >= 0),
  opponent_score integer not null default 0 check (opponent_score >= 0),
  duration_seconds integer check (duration_seconds is null or duration_seconds >= 0),
  feedback smallint check (feedback is null or feedback in (-1, 1)),
  feedback_reason text check (feedback_reason is null or char_length(feedback_reason) <= 120),
  completed_at timestamptz not null default now(),
  feedback_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, play_key)
);

create index if not exists grid_player_history_user_recent_idx
  on public.grid_player_history (user_id, completed_at desc);
create index if not exists grid_player_history_grid_recent_idx
  on public.grid_player_history (grid_id, completed_at desc);
create index if not exists grid_player_history_feedback_idx
  on public.grid_player_history (grid_id, feedback)
  where feedback is not null;

alter table public.grid_player_history enable row level security;
revoke all on table public.grid_player_history from public, anon, authenticated;
grant select, insert, update, delete on table public.grid_player_history to service_role;

create table if not exists public.grid_popularity (
  grid_id text primary key,
  plays integer not null default 0 check (plays >= 0),
  completions integer not null default 0 check (completions >= 0),
  positive_reviews integer not null default 0 check (positive_reviews >= 0),
  negative_reviews integer not null default 0 check (negative_reviews >= 0),
  average_duration_seconds numeric(12,2),
  popularity_score numeric(6,2) not null default 60,
  last_played_at timestamptz,
  updated_at timestamptz not null default now()
);

create index if not exists grid_popularity_score_idx
  on public.grid_popularity (popularity_score desc, plays desc);

alter table public.grid_popularity enable row level security;
revoke all on table public.grid_popularity from public, anon, authenticated;
grant select, insert, update, delete on table public.grid_popularity to service_role;

create table if not exists public.server_grid_rotation_cooldowns (
  answer text primary key,
  reason text not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.server_grid_rotation_cooldowns enable row level security;
revoke all on table public.server_grid_rotation_cooldowns from public, anon, authenticated;
grant select, insert, update, delete on table public.server_grid_rotation_cooldowns to service_role;

insert into public.server_grid_rotation_cooldowns (answer, reason)
select answer, 'Réponse trop fréquente dans le catalogue v13'
from unnest(array[
  'AIR','AMI','ANE','ANS','ARC','BEC','CLE','DO','EAU','ERE','EST','ETE','FER',
  'ICI','IF','IL','ILE','ILES','LIT','MER','NEZ','NON','ON','OR','OS','OUI','PEU',
  'PRE','ROI','SEL','UNIR','VIE','MERS','TES','NOS','MES','MUR'
]) as answer
on conflict (answer) do update
set active = true, reason = excluded.reason, updated_at = now();

create or replace function private.refresh_grid_popularity(p_grid_id text)
returns void
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $$
declare
  v_plays integer;
  v_completions integer;
  v_positive integer;
  v_negative integer;
  v_average_duration numeric(12,2);
  v_last_played timestamptz;
  v_rated integer;
  v_satisfaction numeric;
  v_completion_rate numeric;
  v_confidence numeric;
  v_score numeric(6,2);
begin
  select
    count(*)::integer,
    count(*) filter (where completed)::integer,
    count(*) filter (where feedback = 1)::integer,
    count(*) filter (where feedback = -1)::integer,
    round(avg(duration_seconds)::numeric, 2),
    max(completed_at)
  into v_plays, v_completions, v_positive, v_negative,
       v_average_duration, v_last_played
  from public.grid_player_history
  where grid_id = p_grid_id;

  if v_plays = 0 then
    delete from public.grid_popularity where grid_id = p_grid_id;
    return;
  end if;

  v_rated := v_positive + v_negative;
  -- Bayesian satisfaction starts at 60% over five virtual reviews. This
  -- prevents one early vote from dominating a new grid.
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
    p_grid_id, v_plays, v_completions, v_positive, v_negative,
    v_average_duration, v_score, v_last_played, now()
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

create or replace function private.refresh_grid_popularity_trigger()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $$
begin
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

revoke all on function private.refresh_grid_popularity_trigger() from public, anon, authenticated;

drop trigger if exists refresh_grid_popularity_after_history on public.grid_player_history;
create trigger refresh_grid_popularity_after_history
after insert or update or delete on public.grid_player_history
for each row execute function private.refresh_grid_popularity_trigger();

-- Preserve the already played matches as the beginning of each player's
-- twelve-grid history. Re-running the migration remains idempotent.
insert into public.grid_player_history (
  user_id, play_key, match_id, grid_id, mode, pace, outcome, completed,
  score, opponent_score, duration_seconds, completed_at
)
select
  mp.user_id,
  'match:' || sm.id::text,
  sm.id,
  sm.grid_id,
  case when sm.mode = 'solo' then 'solo' else 'multiplayer' end,
  sm.pace,
  case
    when sm.finish_reason in ('forfeit', 'timeout') and sm.winner_id = mp.user_id then 'opponent-abandoned'
    when sm.finish_reason in ('forfeit', 'timeout') then 'abandon'
    when sm.winner_id is null then 'draw'
    when sm.winner_id = mp.user_id then 'win'
    else 'loss'
  end,
  sm.finish_reason = 'completed',
  greatest(0, coalesce((sm.state -> 'scores' ->> mp.user_id::text)::integer, mp.score, 0)),
  0,
  greatest(0, extract(epoch from (sm.updated_at - sm.created_at))::integer),
  sm.updated_at
from public.match_participants mp
join public.server_matches sm on sm.id = mp.match_id
where sm.status = 'finished'
on conflict (user_id, play_key) do nothing;

do $$
declare v_grid_id text;
begin
  for v_grid_id in select distinct grid_id from public.grid_player_history loop
    perform private.refresh_grid_popularity(v_grid_id);
  end loop;
end;
$$;

;
