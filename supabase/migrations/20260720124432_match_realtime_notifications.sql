-- Realtime only carries a wake-up signal. The authoritative and sanitized
-- match view is still fetched through match-api, so no rack or solution is
-- ever exposed through the websocket channel.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create or replace function private.broadcast_match_update()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform realtime.send(
    jsonb_build_object('updatedAt', new.updated_at),
    'changed',
    'match:' || new.id::text,
    true
  );
  return null;
end;
$$;

revoke all on function private.broadcast_match_update() from public, anon, authenticated;

drop trigger if exists server_matches_broadcast_update on public.server_matches;
create trigger server_matches_broadcast_update
after insert or update on public.server_matches
for each row execute function private.broadcast_match_update();

drop policy if exists "match participants receive updates" on realtime.messages;
create policy "match participants receive updates"
on realtime.messages
for select
to authenticated
using (
  realtime.messages.extension = 'broadcast'
  and exists (
    select 1
    from public.match_participants as participant
    where participant.user_id = (select auth.uid())
      and ('match:' || participant.match_id::text) = (select realtime.topic())
  )
);
