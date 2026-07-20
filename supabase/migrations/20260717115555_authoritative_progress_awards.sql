
create or replace function public.server_award_progress(
  p_user_id uuid,
  p_idempotency_key text,
  p_mode text,
  p_outcome text,
  p_productive_turns integer,
  p_feather_amount integer
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_progress public.player_progress%rowtype;
  current_wallet public.player_wallets%rowtype;
  productive_xp integer;
  completion_xp integer;
  result_xp integer;
  total_xp integer;
  remaining integer;
  goal integer;
  before_level integer;
  next_level integer;
  next_xp integer;
  next_balance bigint;
begin
  if p_mode not in ('solo','multiplayer') or p_outcome not in ('win','draw','loss','abandon','opponent-abandoned') then
    raise exception 'invalid award';
  end if;
  if exists(select 1 from public.experience_awards where user_id=p_user_id and idempotency_key=p_idempotency_key) then
    select * into current_progress from public.player_progress where user_id=p_user_id;
    select * into current_wallet from public.player_wallets where user_id=p_user_id;
    return jsonb_build_object('applied',false,'level',current_progress.level,'xp',current_progress.xp,'feathers',current_wallet.feathers);
  end if;
  select * into current_progress from public.player_progress where user_id=p_user_id for update;
  select * into current_wallet from public.player_wallets where user_id=p_user_id for update;
  before_level := current_progress.level;
  productive_xp := greatest(0,p_productive_turns) * case when p_mode='solo' then 1 else 2 end;
  completion_xp := case when p_outcome in ('win','draw','loss') then case when p_mode='solo' then 5 else 10 end else 0 end;
  result_xp := case
    when p_mode='solo' and p_outcome='win' then 10
    when p_mode='solo' and p_outcome='draw' then 6
    when p_mode='solo' and p_outcome='loss' then 3
    when p_mode='multiplayer' and p_outcome in ('win','opponent-abandoned') then 20
    when p_mode='multiplayer' and p_outcome='draw' then 12
    when p_mode='multiplayer' and p_outcome='loss' then 6
    else 0 end;
  total_xp := productive_xp + completion_xp + result_xp;
  remaining := total_xp;
  next_level := current_progress.level;
  next_xp := current_progress.xp;
  while remaining > 0 and next_level < 50 loop
    goal := 100 + (next_level - 1) * 15;
    if next_xp + remaining >= goal then
      remaining := remaining - (goal - next_xp);
      next_level := next_level + 1;
      next_xp := 0;
    else
      next_xp := next_xp + remaining;
      remaining := 0;
    end if;
  end loop;
  if next_level >= 50 then next_level := 50; next_xp := 0; end if;
  next_balance := current_wallet.feathers + greatest(0,p_feather_amount);
  update public.player_progress set level=next_level,xp=next_xp,lifetime_xp=lifetime_xp+total_xp,
    wins=wins+case when p_outcome in ('win','opponent-abandoned') then 1 else 0 end,
    losses=losses+case when p_outcome='loss' then 1 else 0 end,updated_at=now() where user_id=p_user_id;
  update public.player_wallets set feathers=next_balance,updated_at=now() where user_id=p_user_id;
  insert into public.experience_awards(user_id,idempotency_key,mode,outcome,productive_turns,xp_amount,feather_amount,level_before,level_after)
    values(p_user_id,p_idempotency_key,p_mode,p_outcome,greatest(0,p_productive_turns),total_xp,greatest(0,p_feather_amount),before_level,next_level);
  insert into public.economy_transactions(user_id,idempotency_key,kind,amount,balance_after,metadata)
    values(p_user_id,p_idempotency_key,'match-reward',greatest(0,p_feather_amount),next_balance,jsonb_build_object('mode',p_mode,'outcome',p_outcome));
  return jsonb_build_object('applied',true,'xpAwarded',total_xp,'level',next_level,'xp',next_xp,'feathersAwarded',greatest(0,p_feather_amount),'feathers',next_balance);
end;
$$;
revoke all on function public.server_award_progress(uuid,text,text,text,integer,integer) from public, anon, authenticated;
grant execute on function public.server_award_progress(uuid,text,text,text,integer,integer) to service_role;
;
