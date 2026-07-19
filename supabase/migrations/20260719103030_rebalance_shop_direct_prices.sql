-- Les gains de plumes ont été multipliés par dix. Les achats directs
-- suivent la même échelle, tandis que le panier aléatoire reste à 999.
-- Le filtre rend la mise à niveau sûre si ce SQL est rejoué manuellement.
update public.server_cosmetic_catalog
set price_feathers = price_feathers * 10
where availability = 'epicerie'
  and active = true
  and price_feathers > 0
  and price_feathers < 999;

update public.server_basket_catalog
set price_feathers = 999
where id = 'panier-epicerie';

do $$
begin
  if exists (
    select 1
    from public.server_cosmetic_catalog
    where availability = 'epicerie'
      and active = true
      and price_feathers <= 999
  ) then
    raise exception 'Un achat direct de l''Épicerie reste au prix du panier ou en dessous.';
  end if;
end
$$;
