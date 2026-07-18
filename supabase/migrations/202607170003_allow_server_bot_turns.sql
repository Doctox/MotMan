-- Bots are server-only participants and intentionally have no auth.users row.
-- Match participants still protect every human through match_participants;
-- the current/winner identifiers must therefore also accept server bot UUIDs.
alter table public.server_matches
  drop constraint if exists server_matches_current_player_id_fkey,
  drop constraint if exists server_matches_winner_id_fkey;
