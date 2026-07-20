
create index if not exists match_events_match_id_idx on public.match_events(match_id);
create index if not exists server_match_invitations_match_id_idx on public.server_match_invitations(match_id);
create index if not exists server_matches_winner_id_idx on public.server_matches(winner_id);
;
