-- Défi du jour — RPC de versement PUREMENT MONÉTAIRE.
--
-- POURQUOI UN NOUVEAU RPC : le bonus quotidien ne doit PAS passer par
-- `server_award_progress`. Ce dernier n'est pas monétaire — il recalcule de l'XP
-- (+15 XP parasites pour un solo gagné), incrémente `wins`, journalise en
-- `kind='match-reward'` et peut débloquer des titres. L'utiliser pour un bonus
-- quotidien ajouterait environ 5 475 XP et 365 victoires fantômes par joueur et
-- par an. `server_award_feathers` ne touche donc QUE `player_wallets.feathers` et
-- `economy_transactions`.
--
-- Idempotence : contrainte unique (user_id, idempotency_key) sur
-- `economy_transactions` (migration 20260717114345). Les clés utilisées sont
--   daily:<userId>:<YYYY-MM-DD>          → bonus de complétion, une fois par jour
--   daily-milestone:<userId>:<palier>    → palier de série, une fois par compte
--
-- Le verrou de portefeuille est pris AVANT le contrôle d'idempotence : deux
-- appels concurrents pour le même joueur sont ainsi sérialisés, et le second
-- constate bien la transaction écrite par le premier.

create or replace function public.server_award_feathers(
  p_user_id uuid,
  p_idempotency_key text,
  p_amount integer,
  p_kind text,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_wallet public.player_wallets%rowtype;
  next_balance bigint;
begin
  if p_amount < 0 then
    raise exception 'invalid feather amount';
  end if;
  -- Borne haute : aucun versement quotidien légitime ne dépasse 4 500 plumes
  -- (palier 365 jours). Un montant absurde signale un bug d'appel ; on refuse
  -- plutôt que de créditer un portefeuille de façon irréversible.
  if p_amount > 10000 then
    raise exception 'invalid feather amount';
  end if;
  if p_kind not in ('daily-completion','streak-milestone') then
    raise exception 'invalid feather kind';
  end if;
  if coalesce(p_idempotency_key,'') = '' then
    raise exception 'invalid idempotency key';
  end if;
  if jsonb_typeof(coalesce(p_metadata,'{}'::jsonb)) <> 'object' then
    raise exception 'invalid metadata';
  end if;

  select * into current_wallet from public.player_wallets where user_id=p_user_id for update;
  if current_wallet.user_id is null then
    raise exception 'player wallet missing';
  end if;

  if exists(
    select 1 from public.economy_transactions
    where user_id=p_user_id and idempotency_key=p_idempotency_key
  ) then
    return jsonb_build_object('applied',false,'feathers',current_wallet.feathers);
  end if;

  next_balance := current_wallet.feathers + greatest(0,p_amount);
  update public.player_wallets
    set feathers=next_balance, updated_at=now()
    where user_id=p_user_id;
  insert into public.economy_transactions(user_id,idempotency_key,kind,amount,balance_after,metadata)
  values (p_user_id,p_idempotency_key,p_kind,greatest(0,p_amount),next_balance,coalesce(p_metadata,'{}'::jsonb));

  return jsonb_build_object('applied',true,'feathersAwarded',greatest(0,p_amount),'feathers',next_balance);
end;
$$;

revoke execute on function public.server_award_feathers(uuid,text,integer,text,jsonb) from public,anon,authenticated;
grant execute on function public.server_award_feathers(uuid,text,integer,text,jsonb) to service_role;
