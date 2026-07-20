
create index if not exists matches_current_player on private.matches(current_player_id);
create index if not exists matches_grid on private.matches(grid_id);
create index if not exists matches_winner on private.matches(winner_id);
create index if not exists blocks_blocked on public.blocks(blocked_id);
create index if not exists friendships_right on public.friendships(right_user_id);
create index if not exists match_participants_user on public.match_participants(user_id);
create index if not exists match_participants_opponent on public.match_participants(opponent_id);
create index if not exists reports_reporter on public.reports(reporter_id);
create index if not exists reports_reported on public.reports(reported_id);
create index if not exists reports_reviewer on public.reports(reviewed_by);
;
