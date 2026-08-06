-- Realtime evaluates channel RLS as the connected user. server-side match
-- tables intentionally have no client SELECT grant, so membership must be
-- checked through this narrowly-scoped helper instead of exposing the table.
create or replace function private.is_match_participant(p_topic text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select (select auth.uid()) is not null
    and exists (
      select 1
      from public.match_participants as participant
      where participant.user_id = (select auth.uid())
        and ('match:' || participant.match_id::text) = p_topic
    );
$$;

revoke all on function private.is_match_participant(text) from public, anon;
grant usage on schema private to authenticated;
grant execute on function private.is_match_participant(text) to authenticated;

drop policy if exists "match participants receive updates" on realtime.messages;
create policy "match participants receive updates"
on realtime.messages
for select
to authenticated
using (
  realtime.messages.extension = 'broadcast'
  and private.is_match_participant((select realtime.topic()))
);
