-- Cover every ranked-mode foreign key used by cleanup and lifecycle queries.

create index if not exists ranked_rating_events_opponent_id_idx
  on public.ranked_rating_events(opponent_id);

create index if not exists server_ranked_ready_match_id_idx
  on public.server_ranked_ready_sessions(match_id)
  where match_id is not null;

create index if not exists server_ranked_ready_player_a_paused_match_idx
  on public.server_ranked_ready_sessions(player_a_paused_match_id)
  where player_a_paused_match_id is not null;

create index if not exists server_ranked_ready_player_b_paused_match_idx
  on public.server_ranked_ready_sessions(player_b_paused_match_id)
  where player_b_paused_match_id is not null;

create index if not exists server_ranked_searches_ready_session_idx
  on public.server_ranked_searches(ready_session_id)
  where ready_session_id is not null;
