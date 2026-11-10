---
title: Declare a read Mason can't parse
description: Use depends_on when a gold model's SQL runs on Databricks but Mason can't parse it.
---

Mason finds the tables a gold model reads by parsing its SQL. Some SQL runs on Databricks but doesn't parse, such as a `WATERMARK` clause, and `mason validate` fails with [`MSN203`](../reference/rules/msn203.md):

```sql
SELECT order_id, amount
FROM STREAM(sales.silver.orders)
WATERMARK ordered_at DELAY OF INTERVAL 10 MINUTES
```

```text
MSN203 domains/sales/models/gold/fct_orders.sql: Mason can't read this SQL, so it can't tell what it reads. It doesn't parse near `ordered_at`.
  Fix: Make the file one Databricks SQL query that runs on its own. If it runs on Databricks and Mason still can't parse it, list the tables it reads under `depends_on` in its config file.
```

List the tables it reads under `depends_on`, in the model's config file:

```yaml
kind: model
version: 1
sql: fct_orders.sql
depends_on:
  - sales.silver.orders
```

```text
$ mason validate
Valid.
```

Mason checks each name in `depends_on` as it checks any read: it must be a table in the project, and it must be read in build order. `mason compile` replaces each name wherever it's written in the SQL:

```text
$ mason compile --env dev
...
CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.fct_orders AS
SELECT order_id, amount
FROM STREAM(dev_sales.silver.orders)
WATERMARK ordered_at DELAY OF INTERVAL 10 MINUTES
```

## Each name must be in the SQL as written

Mason finds each name by its exact text, in the same case, and not as part of a longer name. A name that isn't there fails with [`MSN212`](../reference/rules/msn212.md), so `depends_on` can't declare a read the SQL doesn't make:

```text
MSN212 domains/sales/models/gold/fct_orders.yaml: sales.silver.order is in `depends_on`, but fct_orders.sql doesn't have it as written, so Mason can't tell that the SQL reads it.
  Fix: Write sales.silver.order in fct_orders.sql exactly as it is in `depends_on`, or remove it from `depends_on`.
```

> **Note**
> When the SQL doesn't parse, Mason sees only the names in `depends_on`. A table the SQL reads but `depends_on` leaves out isn't checked, and it isn't replaced with each Environment's table. List every table the SQL reads.

When the SQL does parse, Mason reads its tables as usual, and `depends_on` adds to them.

## Next steps

- [Gold Model](../reference/kinds/model.md) lists every field of a model's config file.
