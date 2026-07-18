-- The web client communicates through authenticated Edge Functions only.
-- RLS remains enabled as defence in depth, while direct Data API access is
-- removed so clients cannot bypass validation, rate limits or the economy.
revoke all privileges on all tables in schema public from anon, authenticated;
revoke all privileges on all sequences in schema public from anon, authenticated;

-- Supabase can grant defaults to new objects. Keep future server tables private.
alter default privileges in schema public
  revoke all privileges on tables from anon, authenticated;
alter default privileges in schema public
  revoke all privileges on sequences from anon, authenticated;

-- Economy mutations are callable by the service role inside Edge Functions,
-- never by a browser session.
revoke execute on function public.server_award_progress(uuid, text, text, text, integer, integer) from public, anon, authenticated;
revoke execute on function public.server_purchase_cosmetic(uuid, text, text, text) from public, anon, authenticated;
revoke execute on function public.server_open_basket(uuid, text, text) from public, anon, authenticated;
