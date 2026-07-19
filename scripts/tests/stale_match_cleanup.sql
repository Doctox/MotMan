do $test$
declare
  stale_match_id uuid := gen_random_uuid();
  fresh_match_id uuid := gen_random_uuid();
  active_grid_id text;
begin
  select id into active_grid_id
  from public.server_grid_catalog
  where active is true
  limit 1;

  if active_grid_id is null then
    raise exception 'No active grid available for the retention test';
  end if;

  insert into public.server_matches (
    id, mode, pace, grid_id, state, status, turn_number, created_at, updated_at
  ) values
    (stale_match_id, 'solo', 'async', active_grid_id, '{}'::jsonb, 'active', 1, now() - interval '25 hours', now() - interval '25 hours'),
    (fresh_match_id, 'solo', 'async', active_grid_id, '{}'::jsonb, 'active', 1, now(), now());

  perform private.purge_stale_matches();

  if exists (select 1 from public.server_matches where id = stale_match_id) then
    raise exception 'A stale active match was not deleted';
  end if;

  if not exists (select 1 from public.server_matches where id = fresh_match_id) then
    raise exception 'A fresh active match was deleted';
  end if;

  delete from public.server_matches where id = fresh_match_id;
end;
$test$;
