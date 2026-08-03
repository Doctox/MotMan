-- Correctif E2 — Fiabilise la création de profil invité.
-- Appliqué en production le 2026-08-03 (migration 20260803190706).
--
-- Garde un comportement identique au 1er essai ; en cas de collision de pseudo
-- (ou de friend_code), réessaie avec de l'entropie fraîche jusqu'à 10 fois, au
-- lieu de faire échouer l'inscription. Ne modifie aucune donnée existante :
-- seule la création de NOUVEAUX comptes est concernée.

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_code text := upper(substr(replace(new.id::text, '-', ''), 1, 8));
  v_name text := 'Invité ' || substr(v_code, 1, 4);
  v_attempts integer := 0;
begin
  loop
    begin
      insert into public.profiles(id, display_name, friend_code, account_kind)
      values (new.id, v_name, v_code,
              case when new.is_anonymous then 'guest' else 'account' end);
      exit;
    exception when unique_violation then
      v_attempts := v_attempts + 1;
      if v_attempts >= 10 then
        raise exception 'Profil invité unique introuvable après % tentatives', v_attempts;
      end if;
      v_code := upper(substr(md5(clock_timestamp()::text || new.id::text || v_attempts::text), 1, 8));
      v_name := 'Invité ' || substr(v_code, 1, 6);
    end;
  end loop;

  insert into public.player_progress(user_id) values (new.id);
  insert into public.player_wallets(user_id) values (new.id);
  insert into public.player_inventory(user_id, kind, item_id, source) values
    (new.id, 'avatar', 'plume-motman', 'starter'),
    (new.id, 'frame', 'cadre-ivoire', 'starter'),
    (new.id, 'animation', 'animation-none', 'starter');
  return new;
end;
$$;

revoke all on function private.handle_new_user() from public, anon, authenticated;
