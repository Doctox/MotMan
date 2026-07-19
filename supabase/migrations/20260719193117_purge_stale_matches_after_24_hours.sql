create extension if not exists pg_cron with schema pg_catalog;

create schema if not exists private;

create or replace function private.purge_stale_matches()
returns integer
language plpgsql
security invoker
set search_path = ''
as $$
declare
  deleted_matches integer := 0;
begin
  delete from public.server_match_invitations as invitations
  using public.server_matches as matches
  where invitations.match_id = matches.id
    and matches.updated_at < now() - interval '24 hours';

  delete from public.server_matches
  where updated_at < now() - interval '24 hours';

  get diagnostics deleted_matches = row_count;
  return deleted_matches;
end;
$$;

revoke all on function private.purge_stale_matches() from public, anon, authenticated;

select cron.schedule(
  'motman-purge-stale-matches',
  '23 * * * *',
  'select private.purge_stale_matches();'
);

-- Apply the retention rule immediately as well as on the hourly schedule.
select private.purge_stale_matches();
