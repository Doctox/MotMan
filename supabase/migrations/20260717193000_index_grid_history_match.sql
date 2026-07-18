-- Covers the match foreign key used by history upserts and account cleanup.
create index if not exists grid_player_history_match_idx
  on public.grid_player_history (match_id)
  where match_id is not null;
