-- Keep the opponent label alongside the durable result. server_matches is
-- intentionally purged after 24 hours, while the five-result player history
-- must remain understandable on every device.
alter table public.grid_player_history
  add column if not exists opponent_name text;

alter table public.grid_player_history
  drop constraint if exists grid_player_history_opponent_name_length;
alter table public.grid_player_history
  add constraint grid_player_history_opponent_name_length
  check (opponent_name is null or char_length(opponent_name) between 1 and 32);

-- Preserve bot names for matches that still exist at migration time.
update public.grid_player_history as history
set opponent_name = left(matches.state -> 'bot' ->> 'displayName', 32)
from public.server_matches as matches
where history.match_id = matches.id
  and history.opponent_name is null
  and matches.state -> 'bot' ->> 'displayName' is not null;

-- Preserve human names without exposing the history table to clients.
update public.grid_player_history as history
set opponent_name = left(profiles.display_name, 32)
from public.match_participants as participants
join public.profiles as profiles on profiles.id = participants.user_id
where history.match_id = participants.match_id
  and history.user_id <> participants.user_id
  and history.opponent_name is null;
