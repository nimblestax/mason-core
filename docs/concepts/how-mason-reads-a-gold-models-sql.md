---
title: How Mason reads a gold model's SQL
description: How Mason finds the tables a gold model reads, why `STREAM(...)` makes it a streaming table, what a stream may read, and the SQL Mason can't read yet.
---

A gold model is a SQL file. Mason parses it to find every table it reads, and everything else follows from those reads: the real table names in each environment, which pipelines wait for which, and what `mason validate` checks.

## Reads are logical names, found by parsing

A gold model reads tables by their logical name, three parts: the domain, the layer and the table.

```sql
SELECT o.order_id, o.amount, c.vat_rate
FROM sales.silver.orders AS o
JOIN sales.silver.countries AS c
  ON o.country = c.code
```

Mason parses the query and takes each table it reads, in `FROM`, `JOIN` and subqueries. A CTE's name isn't a table, so it isn't a read. Mason never guesses. Anything that might read a table but isn't a three-part logical name fails `mason validate`:

- a one- or two-part name that isn't a CTE fails with [`MSN201`](../reference/rules/msn201.md)
- a real table name, such as `prod_sales.silver.orders`, fails with [`MSN205`](../reference/rules/msn205.md)
- a name built as the query runs, such as `IDENTIFIER(...)`, fails with [`MSN204`](../reference/rules/msn204.md)
- a read of files, such as `read_files(...)`, fails with [`MSN206`](../reference/rules/msn206.md)
- SQL Mason can't parse fails with [`MSN203`](../reference/rules/msn203.md)

So every table a gold model reads shows in review, and the same SQL works in every environment.

## `STREAM(...)` makes a streaming table

A gold model that reads any table with `STREAM(...)` compiles to a streaming table. Any other gold model compiles to a materialized view. The SQL decides, and there's no setting for it.

```sql
SELECT order_id, amount
FROM STREAM(sales.silver.orders)
```

```sql
CREATE OR REFRESH STREAMING TABLE dev_sales.gold.fct_orders AS
SELECT order_id, amount
FROM STREAM(dev_sales.silver.orders)
```

A streaming table reads only the rows added since its last update. A materialized view reads its whole query each time, and Databricks refreshes it incrementally where it can.

A query that joins a stream to a table read without `STREAM(...)`, such as `STREAM(sales.silver.orders) JOIN sales.silver.countries`, is a streaming table too. Each new order is joined to the countries as they are when it arrives.

## What a stream may read

A stream reads only new rows, so it may read only a table that rows are added to and never changed in place.

| A gold model may stream from | It may not stream from |
| --- | --- |
| silver without `keys` | silver with `keys`, which upserts change in place: [`MSN211`](../reference/rules/msn211.md) |
| a quarantine table | a seed, which is a materialized view: [`MSN212`](../reference/rules/msn212.md) |
| a gold model that streams | a gold model that doesn't stream, which is a materialized view: [`MSN212`](../reference/rules/msn212.md) |

Each of these would otherwise fail in the pipeline, after a deploy. `mason validate` catches them before.

## Known gaps

Databricks accepts some SQL that Mason can't parse yet. Each of these fails `mason validate`, so none reaches a deploy.

- **`WATERMARK ... DELAY OF`** fails with [`MSN203`](../reference/rules/msn203.md). A gold model can't do a watermarked streaming aggregation for now.
- **`STREAM x` without brackets**, as in `JOIN STREAM sales.silver.orders`, fails with [`MSN203`](../reference/rules/msn203.md). Write `STREAM(sales.silver.orders)`.
- **`window(...)` as a table function** fails with [`MSN206`](../reference/rules/msn206.md), because Mason can't see what it reads.
