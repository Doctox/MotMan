-- All application data is now exposed through authenticated Edge Functions.
-- Direct table grants were revoked in 202607170002, so the former client RLS
-- policies are both unreachable and misleading (notably for anonymous Auth
-- sessions). Keep RLS enabled and remove those obsolete access paths.
do $$
declare
  item record;
begin
  for item in
    select schemaname, tablename, policyname
    from pg_policies
    where schemaname = 'public'
  loop
    execute format(
      'drop policy if exists %I on %I.%I',
      item.policyname,
      item.schemaname,
      item.tablename
    );
  end loop;
end
$$;

-- The UNIQUE(user_id, idempotency_key) constraint already owns an identical
-- index, so retaining this manually-created copy only increases write cost.
drop index if exists public.economy_transactions_user_idempotency_uidx;;
