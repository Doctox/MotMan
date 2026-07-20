
alter table public.profiles add column if not exists legacy_imported_at timestamptz;
revoke update on public.profiles from authenticated;
drop policy if exists profiles_update_self on public.profiles;
;
