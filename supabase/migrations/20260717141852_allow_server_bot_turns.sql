alter table public.server_matches
drop constraint if exists server_matches_current_player_id_fkey,
drop constraint if exists server_matches_winner_id_fkey;;
