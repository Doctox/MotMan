-- Google Play requires players to be able to delete their account and its
-- associated data from inside the app. Most player rows already cascade from
-- auth.users; matches need an explicit cleanup because their authoritative
-- state contains player data in JSON.
create or replace function public.server_prepare_account_deletion(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_match_ids uuid[] := array[]::uuid[];
  v_matches_deleted integer := 0;
  v_reports_deleted integer := 0;
begin
  if p_user_id is null then
    raise exception 'Identifiant de compte manquant.';
  end if;

  select coalesce(array_agg(related.id), array[]::uuid[])
  into v_match_ids
  from (
    select participants.match_id as id
    from public.match_participants as participants
    where participants.user_id = p_user_id
       or participants.opponent_id = p_user_id
    union
    select matches.id
    from public.server_matches as matches
    where matches.current_player_id = p_user_id
       or matches.winner_id = p_user_id
  ) as related;

  -- Invitations reference matches without ON DELETE CASCADE.
  delete from public.server_match_invitations
  where host_id = p_user_id
     or guest_id = p_user_id
     or match_id = any(v_match_ids);

  -- A moderator may have reviewed a report before deleting their own account.
  update public.reports set reviewed_by = null where reviewed_by = p_user_id;
  delete from public.reports
  where reporter_id = p_user_id or reported_id = p_user_id;
  get diagnostics v_reports_deleted = row_count;

  delete from public.server_matches where id = any(v_match_ids);
  get diagnostics v_matches_deleted = row_count;

  return jsonb_build_object(
    'matches_deleted', v_matches_deleted,
    'reports_deleted', v_reports_deleted
  );
end;
$$;

revoke all on function public.server_prepare_account_deletion(uuid) from public, anon, authenticated;
grant execute on function public.server_prepare_account_deletion(uuid) to service_role;

comment on function public.server_prepare_account_deletion(uuid) is
  'Deletes non-cascading player data immediately before account-api removes auth.users.';
