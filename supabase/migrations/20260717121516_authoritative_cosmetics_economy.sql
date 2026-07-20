
create table public.server_cosmetic_catalog (
  kind text not null check (kind in ('avatar','frame','animation')),
  item_id text not null,
  name text not null,
  rarity text not null check (rarity in ('commun','singulier','rare','precieux','exceptionnel','legendaire')),
  price_feathers bigint not null check (price_feathers >= 0),
  availability text not null check (availability in ('starter','epicerie','easter-egg')),
  asset text,
  active boolean not null default true,
  updated_at timestamptz not null default now(),
  primary key (kind,item_id)
);
alter table public.server_cosmetic_catalog enable row level security;
revoke all on public.server_cosmetic_catalog from anon, authenticated;
grant all on public.server_cosmetic_catalog to service_role;

create table public.server_basket_catalog (
  id text primary key,
  name text not null,
  price_feathers bigint not null check (price_feathers >= 0),
  active boolean not null default true,
  updated_at timestamptz not null default now()
);
alter table public.server_basket_catalog enable row level security;
revoke all on public.server_basket_catalog from anon, authenticated;
grant all on public.server_basket_catalog to service_role;

create unique index if not exists economy_transactions_user_idempotency_uidx
  on public.economy_transactions(user_id,idempotency_key);
create index if not exists player_inventory_kind_item_idx
  on public.player_inventory(kind,item_id);

create or replace function public.server_purchase_cosmetic(
  p_user_id uuid,
  p_kind text,
  p_item_id text,
  p_idempotency_key text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_price bigint;
  v_balance bigint;
  v_existing jsonb;
begin
  select metadata into v_existing
  from public.economy_transactions
  where user_id=p_user_id and idempotency_key=p_idempotency_key;
  if found then return v_existing; end if;

  select price_feathers into v_price
  from public.server_cosmetic_catalog
  where kind=p_kind and item_id=p_item_id and active and availability='epicerie';
  if not found then raise exception 'Objet indisponible.' using errcode='P0001'; end if;

  if exists(select 1 from public.player_inventory where user_id=p_user_id and kind=p_kind and item_id=p_item_id) then
    raise exception 'Objet déjà possédé.' using errcode='P0001';
  end if;

  select feathers into v_balance
  from public.player_wallets where user_id=p_user_id for update;
  if not found then raise exception 'Portefeuille introuvable.' using errcode='P0001'; end if;
  if v_balance < v_price then raise exception 'Il vous manque quelques plumes.' using errcode='P0001'; end if;

  v_balance := v_balance-v_price;
  update public.player_wallets set feathers=v_balance,updated_at=now() where user_id=p_user_id;
  insert into public.player_inventory(user_id,kind,item_id,source)
    values(p_user_id,p_kind,p_item_id,'shop');
  v_existing := jsonb_build_object('kind',p_kind,'id',p_item_id,'balance',v_balance);
  insert into public.economy_transactions(user_id,idempotency_key,kind,amount,balance_after,metadata)
    values(p_user_id,p_idempotency_key,'shop_purchase',-v_price,v_balance,v_existing);
  return v_existing;
end;
$$;
revoke all on function public.server_purchase_cosmetic(uuid,text,text,text) from public,anon,authenticated;
grant execute on function public.server_purchase_cosmetic(uuid,text,text,text) to service_role;

create or replace function public.server_open_basket(
  p_user_id uuid,
  p_basket_id text,
  p_idempotency_key text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_price bigint;
  v_balance bigint;
  v_pity integer;
  v_kind text;
  v_item_id text;
  v_name text;
  v_rarity text;
  v_asset text;
  v_existing jsonb;
begin
  select metadata into v_existing
  from public.economy_transactions
  where user_id=p_user_id and idempotency_key=p_idempotency_key;
  if found then return v_existing; end if;

  select price_feathers into v_price
  from public.server_basket_catalog where id=p_basket_id and active;
  if not found then raise exception 'Ce panier n''est plus disponible.' using errcode='P0001'; end if;

  select feathers,basket_pity into v_balance,v_pity
  from public.player_wallets where user_id=p_user_id for update;
  if not found then raise exception 'Portefeuille introuvable.' using errcode='P0001'; end if;
  if v_balance < v_price then raise exception 'Il vous manque quelques plumes.' using errcode='P0001'; end if;

  with eligible as (
    select c.*
    from public.server_cosmetic_catalog c
    where c.active and c.availability='epicerie'
      and not exists (
        select 1 from public.player_inventory i
        where i.user_id=p_user_id and i.kind=c.kind and i.item_id=c.item_id
      )
  ), rarity_weights as (
    select rarity,
      case rarity
        when 'commun' then greatest(12.0,50.0-v_pity*2.4)
        when 'singulier' then greatest(14.0,28.0-v_pity*0.7)
        when 'rare' then 14.0+v_pity*1.35
        when 'precieux' then 5.0+v_pity*0.72
        when 'exceptionnel' then 2.5+v_pity*0.31
        else 0.5+v_pity*0.12
      end as weight
    from (select distinct rarity from eligible) r
  ), picked_rarity as (
    select rarity from rarity_weights
    order by -ln(greatest(random(),0.0000001))/weight
    limit 1
  )
  select e.kind,e.item_id,e.name,e.rarity,e.asset
  into v_kind,v_item_id,v_name,v_rarity,v_asset
  from eligible e join picked_rarity p using(rarity)
  order by random() limit 1;

  if v_item_id is null then raise exception 'Votre collection est déjà complète.' using errcode='P0001'; end if;

  v_balance := v_balance-v_price;
  update public.player_wallets
    set feathers=v_balance,
        opened_baskets=opened_baskets+1,
        basket_pity=case when v_rarity in ('rare','precieux','exceptionnel','legendaire') then 0 else least(20,basket_pity+1) end,
        updated_at=now()
    where user_id=p_user_id;
  insert into public.player_inventory(user_id,kind,item_id,source)
    values(p_user_id,v_kind,v_item_id,'basket');
  v_existing := jsonb_build_object(
    'kind',v_kind,'id',v_item_id,'name',v_name,'rarity',v_rarity,
    'asset',v_asset,'balance',v_balance
  );
  insert into public.economy_transactions(user_id,idempotency_key,kind,amount,balance_after,metadata)
    values(p_user_id,p_idempotency_key,'basket_open',-v_price,v_balance,v_existing);
  return v_existing;
end;
$$;
revoke all on function public.server_open_basket(uuid,text,text) from public,anon,authenticated;
grant execute on function public.server_open_basket(uuid,text,text) to service_role;
;
