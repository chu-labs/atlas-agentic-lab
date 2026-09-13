-- Data quality drift: three buildings with claims lose their lot count (migration from a legacy register).
update buildings set lots = 0 where id in (
  select building_id from claims group by building_id order by count(*) desc limit 3
);
