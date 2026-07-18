create table if not exists public.server_title_catalog (
  id text primary key,
  name text not null unique,
  description text not null,
  unlock_type text not null check (unlock_type in ('level','ranked','special')),
  required_value integer not null check (required_value >= 0),
  active boolean not null default true,
  sort_order integer not null default 0,
  updated_at timestamptz not null default now(),
  unique (unlock_type, required_value)
);

create table if not exists public.player_titles (
  user_id uuid not null references auth.users(id) on delete cascade,
  title_id text not null references public.server_title_catalog(id) on delete cascade,
  source text not null check (source in ('level','ranked','special')),
  unlocked_at timestamptz not null default now(),
  primary key (user_id, title_id)
);

alter table public.profiles
  add column if not exists title_id text references public.server_title_catalog(id) on delete set null;

alter table public.experience_awards
  add column if not exists feather_breakdown jsonb not null default '{}'::jsonb,
  add column if not exists unlocked_title_ids text[] not null default '{}'::text[];

alter table public.server_title_catalog enable row level security;
alter table public.player_titles enable row level security;
revoke all on table public.server_title_catalog, public.player_titles from public, anon, authenticated;
grant all on table public.server_title_catalog, public.player_titles to service_role;

insert into public.server_title_catalog(id,name,description,unlock_type,required_value,sort_order) values
  ('premiers-mots','Premiers mots','Les premières lettres de votre aventure.','level',1,10),
  ('plume-curieuse','Plume curieuse','Toujours prêt à chercher le mot juste.','level',5,20),
  ('amoureux-des-mots','Amoureux des mots','Les mots sont devenus un terrain de jeu.','level',10,30),
  ('esprit-lettre','Esprit lettré','Une pensée fine et un vocabulaire sûr.','level',15,40),
  ('plume-affutee','Plume affûtée','Chaque définition trouve sa réponse.','level',20,50),
  ('tisseur-de-mots','Tisseur de mots','Les croisements n’ont presque plus de secrets.','level',25,60),
  ('virtuose-des-lettres','Virtuose des lettres','Les lettres s’accordent avec élégance.','level',30,70),
  ('maitre-des-mots','Maître des mots','Une maîtrise patiente et redoutable.','level',35,80),
  ('sage-du-lexique','Sage du lexique','Un grand voyage au cœur du français.','level',40,90),
  ('gardien-des-mots','Gardien des mots','Les mots peuvent compter sur vous.','level',45,100),
  ('legende-de-motman','Légende de MotMan','Le plus haut titre de la progression.','level',50,110)
on conflict (id) do update set
  name=excluded.name,
  description=excluded.description,
  unlock_type=excluded.unlock_type,
  required_value=excluded.required_value,
  sort_order=excluded.sort_order,
  active=true,
  updated_at=now();

insert into public.player_titles(user_id,title_id,source)
select progress.user_id,title.id,'level'
from public.player_progress progress
join public.server_title_catalog title
  on title.active and title.unlock_type='level' and title.required_value <= progress.level
on conflict do nothing;

update public.profiles
set title_id='premiers-mots',updated_at=now()
where title_id is null;

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  suffix text := upper(substr(replace(new.id::text, '-', ''), 1, 8));
begin
  insert into public.profiles(id, display_name, friend_code, account_kind, title_id)
  values (new.id, 'Invité ' || substr(suffix, 1, 4), suffix, case when new.is_anonymous then 'guest' else 'account' end, 'premiers-mots');
  insert into public.player_progress(user_id) values (new.id);
  insert into public.player_wallets(user_id) values (new.id);
  insert into public.player_inventory(user_id, kind, item_id, source) values
    (new.id, 'avatar', 'plume-motman', 'starter'),
    (new.id, 'frame', 'cadre-ivoire', 'starter'),
    (new.id, 'animation', 'animation-none', 'starter');
  insert into public.player_titles(user_id,title_id,source)
  values (new.id,'premiers-mots','level');
  return new;
end;
$$;

create or replace function public.server_award_progress(
  p_user_id uuid,
  p_idempotency_key text,
  p_mode text,
  p_outcome text,
  p_productive_turns integer,
  p_feather_amount integer,
  p_feather_breakdown jsonb
)
returns jsonb
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
  new_title_ids text[] := '{}'::text[];
begin
  if p_mode not in ('solo','multiplayer') or p_outcome not in ('win','draw','loss','abandon','opponent-abandoned') then
    raise exception 'invalid award';
  end if;
  if p_feather_amount < 0 or jsonb_typeof(coalesce(p_feather_breakdown,'{}'::jsonb)) <> 'object' then
    raise exception 'invalid feather reward';
  end if;
  if exists(select 1 from public.experience_awards where user_id=p_user_id and idempotency_key=p_idempotency_key) then
    select * into current_progress from public.player_progress where user_id=p_user_id;
    select * into current_wallet from public.player_wallets where user_id=p_user_id;
    return jsonb_build_object('applied',false,'level',current_progress.level,'xp',current_progress.xp,'feathers',current_wallet.feathers);
  end if;

  select * into current_progress from public.player_progress where user_id=p_user_id for update;
  select * into current_wallet from public.player_wallets where user_id=p_user_id for update;
  if current_progress.user_id is null or current_wallet.user_id is null then
    raise exception 'player progression missing';
  end if;
  before_level := current_progress.level;
  productive_xp := greatest(0,p_productive_turns) * case when p_mode='solo' then 1 else 2 end;
  completion_xp := case when p_outcome in ('win','draw','loss') then case when p_mode='solo' then 5 else 10 end else 0 end;
  result_xp := case
    when p_mode='solo' and p_outcome='win' then 10
    when p_mode='solo' and p_outcome='draw' then 6
    when p_mode='solo' and p_outcome='loss' then 3
    when p_mode='multiplayer' and p_outcome='win' then 20
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

  update public.player_progress set
    level=next_level,
    xp=next_xp,
    lifetime_xp=lifetime_xp+total_xp,
    wins=wins+case when p_outcome in ('win','opponent-abandoned') then 1 else 0 end,
    losses=losses+case when p_outcome in ('loss','abandon') then 1 else 0 end,
    updated_at=now()
  where user_id=p_user_id;
  update public.player_wallets set feathers=next_balance,updated_at=now() where user_id=p_user_id;

  with newly_unlocked as (
    insert into public.player_titles(user_id,title_id,source)
    select p_user_id,title.id,'level'
    from public.server_title_catalog title
    where title.active and title.unlock_type='level' and title.required_value <= next_level
    on conflict do nothing
    returning title_id
  )
  select coalesce(array_agg(title_id order by title_id),'{}'::text[])
  into new_title_ids
  from newly_unlocked;

  update public.profiles
  set title_id=coalesce(title_id,'premiers-mots'),updated_at=now()
  where id=p_user_id;

  insert into public.experience_awards(
    user_id,idempotency_key,mode,outcome,productive_turns,xp_amount,feather_amount,
    feather_breakdown,unlocked_title_ids,level_before,level_after
  ) values (
    p_user_id,p_idempotency_key,p_mode,p_outcome,greatest(0,p_productive_turns),total_xp,
    greatest(0,p_feather_amount),coalesce(p_feather_breakdown,'{}'::jsonb),new_title_ids,before_level,next_level
  );
  insert into public.economy_transactions(user_id,idempotency_key,kind,amount,balance_after,metadata)
  values(
    p_user_id,p_idempotency_key,'match-reward',greatest(0,p_feather_amount),next_balance,
    jsonb_build_object('mode',p_mode,'outcome',p_outcome,'breakdown',coalesce(p_feather_breakdown,'{}'::jsonb))
  );
  return jsonb_build_object(
    'applied',true,'xpAwarded',total_xp,'level',next_level,'xp',next_xp,
    'feathersAwarded',greatest(0,p_feather_amount),'feathers',next_balance,'unlockedTitleIds',new_title_ids
  );
end;
$$;

-- Compatibility while the previous Edge Function version is being replaced.
create or replace function public.server_award_progress(
  p_user_id uuid,
  p_idempotency_key text,
  p_mode text,
  p_outcome text,
  p_productive_turns integer,
  p_feather_amount integer
)
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select public.server_award_progress(
    p_user_id,p_idempotency_key,p_mode,p_outcome,p_productive_turns,p_feather_amount,
    jsonb_build_object('base',greatest(0,p_feather_amount),'noHint',0,'noReroll',0,'fullRack',0,'total',greatest(0,p_feather_amount))
  );
$$;

revoke execute on function public.server_award_progress(uuid,text,text,text,integer,integer,jsonb) from public,anon,authenticated;
revoke execute on function public.server_award_progress(uuid,text,text,text,integer,integer) from public,anon,authenticated;
grant execute on function public.server_award_progress(uuid,text,text,text,integer,integer,jsonb) to service_role;
grant execute on function public.server_award_progress(uuid,text,text,text,integer,integer) to service_role;
