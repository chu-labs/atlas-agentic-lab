-- Data quality drift: three buildings in the current renewal window lose their lot count
-- (a legacy register migration). Renewal-season traffic quotes and risk-checks these first.
update buildings set lots = 0 where id in (
  select b.id from buildings b
  join policies p on p.building_id = b.id and p.status = 'active'
    and p.expiry_date between current_date and current_date + 30
  join claims c on c.building_id = b.id
  group by b.id order by count(c.id) desc limit 3
);
