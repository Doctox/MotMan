-- Async turns expire after 24 hours, but their rows remain recoverable for a
-- two-hour technical grace period. This prevents a late timeout resolution
-- from racing the physical cleanup job.
create or replace function private.purge_stale_matches()
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  deleted_matches integer := 0;
  stale_match_ids uuid[] := '{}'::uuid[];
begin
  -- Lock the exact cleanup set for the duration of this short transaction.
  -- A match being resolved concurrently is skipped and reconsidered by the
  -- next hourly run instead of losing its invitation halfway through cleanup.
  select coalesce(array_agg(stale.id), '{}'::uuid[])
  into stale_match_ids
  from (
    select matches.id
    from public.server_matches as matches
    where matches.updated_at < now() - interval '26 hours'
    order by matches.updated_at, matches.id
    for update skip locked
  ) as stale;

  if cardinality(stale_match_ids) = 0 then
    return 0;
  end if;

  delete from public.server_match_invitations
  where match_id = any(stale_match_ids);

  delete from public.server_matches
  where id = any(stale_match_ids);

  get diagnostics deleted_matches = row_count;
  return deleted_matches;
end;
$$;

revoke all on function private.purge_stale_matches() from public, anon, authenticated;

comment on function private.purge_stale_matches() is
  'Purges matches after 26 hours of inactivity, leaving a two-hour margin after the 24-hour async turn deadline.';
