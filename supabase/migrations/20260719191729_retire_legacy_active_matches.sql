-- Remove every match created with a grid outside the final 7x8 catalogue.
-- Invitations keep a non-cascading reference to matches, so delete those
-- records first. Participants/events cascade and history match_id becomes null.
delete from public.server_match_invitations as invitations
using public.server_matches as matches, public.server_grid_catalog as grids
where invitations.match_id = matches.id
  and matches.grid_id = grids.id
  and (
    grids.active is not true
    or grids.columns <> 7
    or grids.rows <> 8
  );

delete from public.server_matches as matches
using public.server_grid_catalog as grids
where matches.grid_id = grids.id
  and (
    grids.active is not true
    or grids.columns <> 7
    or grids.rows <> 8
  );
