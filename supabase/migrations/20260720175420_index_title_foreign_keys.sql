-- Foreign-key indexes recommended by the Supabase Database Advisor.
-- They speed up title joins and the referential checks performed when a title
-- is updated or deleted.
create index if not exists player_titles_title_id_idx
  on public.player_titles (title_id);

create index if not exists profiles_title_id_idx
  on public.profiles (title_id);
