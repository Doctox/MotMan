-- The menu receives wake-up pulses only. Authoritative social and match data
-- stays behind the JWT-protected Edge Functions.
create or replace function private.broadcast_user_menu_wakeup(
  p_user_id uuid,
  p_scope text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_user_id is null then
    return;
  end if;

  perform realtime.send(
    jsonb_build_object(
      'scope', case when p_scope in ('lobby', 'social') then p_scope else 'all' end,
      'updatedAt', clock_timestamp()
    ),
    'changed',
    'user:' || p_user_id::text,
    true
  );
end;
$$;

revoke all on function private.broadcast_user_menu_wakeup(uuid, text)
from public, anon, authenticated;

create or replace function private.broadcast_friend_request_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.from_user_id, 'social');
    perform private.broadcast_user_menu_wakeup(new.to_user_id, 'social');
  end if;
  if tg_op = 'DELETE'
     or (tg_op = 'UPDATE' and (
       old.from_user_id is distinct from new.from_user_id
       or old.to_user_id is distinct from new.to_user_id
     )) then
    perform private.broadcast_user_menu_wakeup(old.from_user_id, 'social');
    perform private.broadcast_user_menu_wakeup(old.to_user_id, 'social');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_friendship_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.left_user_id, 'social');
    perform private.broadcast_user_menu_wakeup(new.right_user_id, 'social');
  else
    perform private.broadcast_user_menu_wakeup(old.left_user_id, 'social');
    perform private.broadcast_user_menu_wakeup(old.right_user_id, 'social');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_block_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.owner_id, 'social');
    perform private.broadcast_user_menu_wakeup(new.blocked_id, 'social');
  else
    perform private.broadcast_user_menu_wakeup(old.owner_id, 'social');
    perform private.broadcast_user_menu_wakeup(old.blocked_id, 'social');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_invitation_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.host_id, 'lobby');
    perform private.broadcast_user_menu_wakeup(new.guest_id, 'lobby');
  end if;
  if tg_op = 'DELETE'
     or (tg_op = 'UPDATE' and (
       old.host_id is distinct from new.host_id
       or old.guest_id is distinct from new.guest_id
     )) then
    perform private.broadcast_user_menu_wakeup(old.host_id, 'lobby');
    perform private.broadcast_user_menu_wakeup(old.guest_id, 'lobby');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_search_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.user_id, 'lobby');
  else
    perform private.broadcast_user_menu_wakeup(old.user_id, 'lobby');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_participant_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.user_id, 'lobby');
  else
    perform private.broadcast_user_menu_wakeup(old.user_id, 'lobby');
  end if;
  return null;
end;
$$;

create or replace function private.broadcast_match_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  participant record;
begin
  for participant in
    select match_participant.user_id
    from public.match_participants as match_participant
    where match_participant.match_id = new.id
  loop
    perform private.broadcast_user_menu_wakeup(participant.user_id, 'lobby');
  end loop;
  return null;
end;
$$;

create or replace function private.broadcast_history_menu_wakeup()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op <> 'DELETE' then
    perform private.broadcast_user_menu_wakeup(new.user_id, 'lobby');
  end if;
  if tg_op = 'DELETE'
     or (tg_op = 'UPDATE' and old.user_id is distinct from new.user_id) then
    perform private.broadcast_user_menu_wakeup(old.user_id, 'lobby');
  end if;
  return null;
end;
$$;

revoke all on function private.broadcast_friend_request_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_friendship_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_block_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_invitation_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_search_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_participant_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_match_menu_wakeup()
from public, anon, authenticated;
revoke all on function private.broadcast_history_menu_wakeup()
from public, anon, authenticated;

drop trigger if exists friend_requests_menu_wakeup on public.friend_requests;
create trigger friend_requests_menu_wakeup
after insert or update or delete on public.friend_requests
for each row execute function private.broadcast_friend_request_menu_wakeup();

drop trigger if exists friendships_menu_wakeup on public.friendships;
create trigger friendships_menu_wakeup
after insert or delete on public.friendships
for each row execute function private.broadcast_friendship_menu_wakeup();

drop trigger if exists blocks_menu_wakeup on public.blocks;
create trigger blocks_menu_wakeup
after insert or delete on public.blocks
for each row execute function private.broadcast_block_menu_wakeup();

drop trigger if exists match_invitations_menu_wakeup on public.server_match_invitations;
create trigger match_invitations_menu_wakeup
after insert or update or delete on public.server_match_invitations
for each row execute function private.broadcast_invitation_menu_wakeup();

drop trigger if exists match_searches_menu_wakeup on public.server_match_searches;
create trigger match_searches_menu_wakeup
after insert or update or delete on public.server_match_searches
for each row execute function private.broadcast_search_menu_wakeup();

drop trigger if exists match_participants_menu_wakeup on public.match_participants;
create trigger match_participants_menu_wakeup
after insert or delete on public.match_participants
for each row execute function private.broadcast_participant_menu_wakeup();

drop trigger if exists server_matches_menu_wakeup on public.server_matches;
create trigger server_matches_menu_wakeup
after update on public.server_matches
for each row execute function private.broadcast_match_menu_wakeup();

drop trigger if exists grid_history_menu_wakeup on public.grid_player_history;
create trigger grid_history_menu_wakeup
after insert or update or delete on public.grid_player_history
for each row execute function private.broadcast_history_menu_wakeup();

drop policy if exists "users receive their menu wakeups" on realtime.messages;
create policy "users receive their menu wakeups"
on realtime.messages
for select
to authenticated
using (
  realtime.messages.extension = 'broadcast'
  and (select realtime.topic()) = ('user:' || (select auth.uid())::text)
);
