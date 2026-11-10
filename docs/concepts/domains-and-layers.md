---
title: Domains and layers
description: How a domain owns its tables, why bronze and silver are fixed, and how you name your own model layers.
---

Every table in a Mason project belongs to one domain and one layer. Together with the table's own name, they make its logical name, `<domain>.<layer>.<table>`, such as `sales.silver.orders`. Your SQL reads tables by logical name, and Mason resolves each one to a real catalog and schema in every environment.

## Domains

A domain is a unit of ownership and access. It owns a set of sources, seeds and gold models, and each domain is a folder under `domains/`, listed in `domains` in `mason.platform.yaml`:

```yaml
domains:
  - sales
  - finance
```

A domain can follow a business area, such as `sales`, or a source system, such as `salesforce`. With a domain per source system, bronze and silver are aligned to the systems your data comes from, and gold is aligned to the teams that use it:

```text
domains/
  salesforce/
    sources/accounts.yaml      # salesforce.bronze.accounts, salesforce.silver.accounts
  sales/
    models/gold/dim_account.yaml   # sales.gold.dim_account
```

The `layer-catalogs` [naming style](naming.md) suits this layout, because each layer gets its own catalog and each domain a schema inside it: `prod_silver.salesforce.accounts` and `prod_gold.sales.dim_account`.

A domain reads its own tables freely. From other domains, it reads only silver they have exported and gold in the shared domain. See [`MSN209`](../reference/rules/msn209.md).

## Source layers: bronze and silver

Every source makes two tables, in two layers that are always called `bronze` and `silver`:

- Bronze keeps rows as they landed. Only its own silver reads it.
- Silver is typed, deduplicated by key, and checked against [expectations](expectations.md). Gold models read silver.

Mason decides what each of these layers does, so you can't rename them, add a third or remove one. If you need another step after silver, add a model layer. `mason.platform.yaml` has no field for them. A version 1 file, written by an older Mason, may still list them as `sources: [bronze, silver]`, which is accepted. Any other value fails with [`MSN125`](../reference/rules/msn125.md).

Seeds sit in silver too.

## Model layers

Gold models fill model layers, and you name them. A new project has one, `gold`:

```yaml
naming:
  style: domain-catalogs
  layers:
    models: [gold]
```

Add more to shape gold for the people who use it, such as `marts` or `serving`:

```yaml
  layers:
    models: [gold, marts]
```

Each model layer is a schema in every domain, so `sales.marts.fct_orders` is a table in the `marts` schema next to `sales.gold`. A model layer adds a schema, not a pipeline: each domain still has one ingest pipeline and one gold pipeline, and the gold pipeline builds each table after the tables it reads.

Model layers have no order. A gold model can read any model layer in its own domain, in either direction, so a model in `marts` can read `gold`, and a model in `gold` can read `marts`. The order you list them in changes nothing. What Mason refuses is a loop, where gold models read each other and none can be built first, even when the loop crosses layers. See [`MSN208`](../reference/rules/msn208.md).

A model layer can't be called `bronze` or `silver`. See [`MSN126`](../reference/rules/msn126.md).

## A gold model's folder sets its layer

A gold model's layer is the first folder under its domain's `models/` folder. There is no `layer` field:

```text
domains/sales/models/gold/fct_orders.yaml    # sales.gold.fct_orders
domains/sales/models/marts/fct_orders.yaml   # sales.marts.fct_orders
```

So a gold model's path reads as its logical name. The two files above are two tables, because they are in two layers.

A file directly in `models/`, or in a first folder that isn't a model layer, fails with [`MSN127`](../reference/rules/msn127.md), which lists your model layers.

## Folders that only group files

Folders below a model layer's folder, and any folders under `sources/` and `seeds/`, group files and nothing more. Mason reads them at any depth, and they don't change a table's name, schema or anything else:

```text
domains/sales/sources/erp/eu/orders.yaml          # sales.silver.orders
domains/sales/models/gold/finance/revenue.yaml    # sales.gold.revenue
```

Because these folders carry no meaning, two files with one name in one domain's layer would be one table, and fail with [`MSN120`](../reference/rules/msn120.md).
