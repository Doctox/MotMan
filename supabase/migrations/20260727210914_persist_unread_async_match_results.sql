-- A completed asynchronous match must remain visible to each player until
-- that player explicitly leaves its result screen. The durable history row
-- survives the short-lived server_matches row, so the acknowledgement also
-- works after the technical match purge.
alter table public.grid_player_history
  add column if not exists finish_reason text,
  add column if not exists result_acknowledged_at timestamptz;

alter table public.grid_player_history
  drop constraint if exists grid_player_history_finish_reason_check;
alter table public.grid_player_history
  add constraint grid_player_history_finish_reason_check
  check (finish_reason is null or finish_reason in ('completed', 'timeout', 'forfeit'));

-- Do not surface the entire historical catalogue as unread when this feature
-- is installed. Only results recorded after the migration start unread.
update public.grid_player_history
set
  finish_reason = coalesce(
    finish_reason,
    case
      when outcome in ('abandon', 'opponent-abandoned') then 'forfeit'
      else 'completed'
    end
  ),
  result_acknowledged_at = coalesce(result_acknowledged_at, now())
where finish_reason is null
   or result_acknowledged_at is null;

create index if not exists grid_player_history_unread_async_result_idx
  on public.grid_player_history (user_id, completed_at)
  where pace = 'async' and result_acknowledged_at is null;

comment on column public.grid_player_history.finish_reason is
  'Authoritative reason used to reconstruct a durable result screen after server match cleanup.';
comment on column public.grid_player_history.result_acknowledged_at is
  'Per-player acknowledgement set only after an explicit action on the result screen.';
