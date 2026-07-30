-- The public ranked RPCs deliberately run as SECURITY INVOKER. They are only
-- executable by service_role, so that role must also be able to call the
-- small private helpers used by those RPCs.
--
-- Do not grant these privileges to anon/authenticated: ranked state changes
-- must continue to pass through match-api.

grant usage on schema private to service_role;

grant execute on function private.ranked_effective_points(integer, integer)
  to service_role;
grant execute on function private.ranked_tier_index(integer)
  to service_role;
grant execute on function private.pause_realtime_normal_for_ranked(uuid, uuid)
  to service_role;
grant execute on function private.resume_ranked_paused_match(uuid, uuid)
  to service_role;
grant execute on function private.finish_ranked_transfer_match(uuid, uuid)
  to service_role;
