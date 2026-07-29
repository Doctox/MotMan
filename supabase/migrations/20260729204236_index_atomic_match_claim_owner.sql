create index if not exists server_match_searches_claimed_by_idx
  on public.server_match_searches(claimed_by)
  where claimed_by is not null;
