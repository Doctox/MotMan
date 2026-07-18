-- The first prototype stored matches and full grids in private.* tables.
-- The authoritative runtime now exclusively uses public.server_* tables
-- through authenticated Edge Functions. Keeping the obsolete copy would
-- preserve a second, untested path around the server game engine.
drop table if exists private.match_invitations;
drop table if exists private.match_searches;
drop table if exists private.matches;
drop table if exists private.grid_catalog;
