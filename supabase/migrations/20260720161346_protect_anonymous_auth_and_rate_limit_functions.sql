-- Abuse protection shared by every Edge Function. Keeping the counters in
-- Postgres makes the limit atomic and independent from Edge isolate restarts.
create table if not exists public.server_rate_limits (
  subject_id uuid not null references auth.users(id) on delete cascade,
  bucket text not null,
  request_count integer not null default 0 check (request_count >= 0),
  window_started_at timestamptz not null default now(),
  expires_at timestamptz not null,
  primary key (subject_id, bucket),
  constraint server_rate_limits_bucket_format
    check (bucket ~ '^[a-z0-9:_-]{1,96}$')
);

create index if not exists server_rate_limits_expiry_idx
  on public.server_rate_limits (expires_at);

alter table public.server_rate_limits enable row level security;
revoke all on table public.server_rate_limits from public, anon, authenticated;
grant select, insert, update, delete on table public.server_rate_limits to service_role;

create or replace function public.server_consume_rate_limit(
  p_subject_id uuid,
  p_bucket text,
  p_max_requests integer,
  p_window_seconds integer
)
returns table (
  allowed boolean,
  remaining integer,
  retry_after_seconds integer
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := clock_timestamp();
  v_count integer;
  v_expires_at timestamptz;
begin
  if p_subject_id is null then
    raise exception 'Rate-limit subject is required.';
  end if;
  if p_bucket is null or p_bucket !~ '^[a-z0-9:_-]{1,96}$' then
    raise exception 'Invalid rate-limit bucket.';
  end if;
  if p_max_requests < 1 or p_max_requests > 10000 then
    raise exception 'Invalid rate-limit maximum.';
  end if;
  if p_window_seconds < 1 or p_window_seconds > 86400 then
    raise exception 'Invalid rate-limit window.';
  end if;

  insert into public.server_rate_limits as limits (
    subject_id,
    bucket,
    request_count,
    window_started_at,
    expires_at
  ) values (
    p_subject_id,
    p_bucket,
    1,
    v_now,
    v_now + make_interval(secs => p_window_seconds)
  )
  on conflict (subject_id, bucket) do update
  set request_count = case
        when limits.expires_at <= v_now then 1
        else limits.request_count + 1
      end,
      window_started_at = case
        when limits.expires_at <= v_now then v_now
        else limits.window_started_at
      end,
      expires_at = case
        when limits.expires_at <= v_now then v_now + make_interval(secs => p_window_seconds)
        else limits.expires_at
      end
  returning limits.request_count, limits.expires_at
  into v_count, v_expires_at;

  allowed := v_count <= p_max_requests;
  remaining := greatest(0, p_max_requests - v_count);
  retry_after_seconds := case
    when allowed then 0
    else greatest(1, ceil(extract(epoch from (v_expires_at - v_now)))::integer)
  end;
  return next;
end;
$$;

revoke all on function public.server_consume_rate_limit(uuid, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.server_consume_rate_limit(uuid, text, integer, integer)
  to service_role;

comment on table public.server_rate_limits is
  'Server-only fixed-window counters used by MotMan Edge Functions.';
comment on function public.server_consume_rate_limit(uuid, text, integer, integer) is
  'Atomically consumes one request from a server-only per-user rate-limit bucket.';

create schema if not exists private;

-- Supabase does not automatically remove abandoned anonymous identities.
-- Delete only guests inactive for 30 days, in small batches, and never while
-- they still participate in an active match.
create or replace function private.cleanup_inactive_guests(p_batch_size integer default 100)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_deleted_guests integer := 0;
  v_deleted_limits integer := 0;
begin
  if p_batch_size < 1 or p_batch_size > 500 then
    raise exception 'Invalid cleanup batch size.';
  end if;

  delete from public.server_rate_limits
  where expires_at < now() - interval '1 day';
  get diagnostics v_deleted_limits = row_count;

  for v_user_id in
    select users.id
    from auth.users as users
    left join public.profiles as profiles on profiles.id = users.id
    where users.is_anonymous is true
      and greatest(
        coalesce(users.last_sign_in_at, users.created_at),
        coalesce(profiles.last_seen, users.created_at)
      ) < now() - interval '30 days'
      and not exists (
        select 1
        from public.match_participants as participants
        join public.server_matches as matches on matches.id = participants.match_id
        where matches.status = 'active'
          and (participants.user_id = users.id or participants.opponent_id = users.id)
      )
    order by users.created_at, users.id
    limit p_batch_size
    for update of users skip locked
  loop
    perform public.server_prepare_account_deletion(v_user_id);
    delete from auth.users where id = v_user_id and is_anonymous is true;
    if found then v_deleted_guests := v_deleted_guests + 1; end if;
  end loop;

  return jsonb_build_object(
    'deleted_guests', v_deleted_guests,
    'deleted_rate_limits', v_deleted_limits
  );
end;
$$;

revoke all on function private.cleanup_inactive_guests(integer)
  from public, anon, authenticated;

comment on function private.cleanup_inactive_guests(integer) is
  'Daily bounded cleanup of anonymous users inactive for 30 days and expired rate-limit counters.';

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid from cron.job where jobname = 'motman-cleanup-inactive-guests'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
end;
$$;

select cron.schedule(
  'motman-cleanup-inactive-guests',
  '17 3 * * *',
  'select private.cleanup_inactive_guests(100);'
);
