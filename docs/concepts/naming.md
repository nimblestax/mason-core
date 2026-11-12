---
title: Naming
description: The three naming styles, how a logical name becomes a real table name in each environment, and what to do when none of them fits.
---

Your SQL reads tables by logical name, such as `sales.silver.orders`: the domain, the layer and the table. Mason turns each logical name into a real catalog, schema and table for the environment it deploys to. The naming style in `mason.platform.yaml` says how.

```yaml
naming:
  style: domain-catalogs
  layers:
    models: [gold]
```

`mason init` asks for the style and writes it here. Pressing Enter takes `domain-catalogs`.

## The three styles

Each style puts the environment first, then the domain and the layer, and joins the parts with `_`.

| Style | Catalog | Schema | `sales.silver.orders` in prod |
| --- | --- | --- | --- |
| `domain-catalogs` | `<env>_<domain>` | `<layer>` | `prod_sales.silver.orders` |
| `layer-catalogs` | `<env>_<layer>` | `<domain>` | `prod_silver.sales.orders` |
| `environment-catalogs` | `<env>` | `<domain>_<layer>` | `prod.sales_silver.orders` |

- `domain-catalogs` gives each domain its own catalog in each environment. A domain's owners get one catalog to grant on, and its layers are schemas inside it. This is the style the Nimblestax Way recommends.
- `layer-catalogs` gives each layer its own catalog, with a schema per domain. It suits teams that grant by layer, and teams whose domains are source systems.
- `environment-catalogs` puts each environment in one catalog, with a schema for each domain and layer. It suits a workspace where you can create only a few catalogs.

Every style works with one workspace for all environments, or one workspace per environment. The environment is always part of the catalog name, so environments sharing a workspace never share a table.

On one workspace, the production environment is kept apart from the others by its catalogs, each environment's CI identity and their grants. See [Environments](environments.md#one-shared-workspace).

## How a logical name resolves

The SQL is the same in every environment. Only the real name changes. With `domain-catalogs`, `sales.silver.orders` is:

| Environment | Real table |
| --- | --- |
| `dev` | `dev_sales.silver.orders` |
| `test` | `test_sales.silver.orders` |
| `prod` | `prod_sales.silver.orders` |

Each domain and layer pair gets its own catalog and schema. A gold model in the same project, `sales.gold.fct_orders`, is `prod_sales.gold.fct_orders` in prod, and a finance source, `finance.silver.invoices`, is `prod_finance.silver.invoices`.

`mason init` prints every catalog and schema your project needs, so you can create them before your first deploy. Mason never creates them. `mason compile --env prod` shows the real names in the code it generates.

`mason validate --platform` signs in to an environment's workspace and checks that its catalogs and schemas are there, so a missing one fails before a deploy rather than halfway through one. It checks the default environment, or the one `--env` names:

```console
$ mason validate --platform --env dev
MSN302 mason.platform.yaml: The schema `dev_sales.silver` isn't in dev's workspace, https://kettle.cloud.databricks.com, or the identity Mason signed in as can't see it. The project's tables in dev need it.
  Fix: Create the schema `silver` in the catalog `dev_sales`, or grant the identity `USE SCHEMA` on it. Mason never creates schemas.
```

It checks one environment at a time, because each CI job signs in as one environment's identity. The workflows `mason init --ci github` writes run it as dev, before anything else. Plain `mason validate` reads no workspace.

## Changing the style

Before your first deploy, change the style by editing that one word.

> **Warning**
> After a deploy, a new style gives every table a new catalog or schema. The next deploy creates empty tables there and leaves the old ones where they are. Mason doesn't stop this yet, so don't change the style of a deployed project.

## When none of these fit

You name the environments, the domains and the model layers yourself, so most conventions fit one of the styles. A prefix is part of the name you choose. If your catalogs start with `acme_prod`, name the environment `acme_prod`, and `domain-catalogs` gives `acme_prod_sales.silver.orders`. For now, the environment you develop in must still be called `dev`.

Mason fixes two things:

- **The environment comes first.** Catalogs then sort by environment, so when you review grants, everything in prod sits together.
- **Every environment, domain and layer gets its own catalog and schema.** Grants, expectations and quarantine all apply per schema, so two domains or two layers in one schema would share them. Two environments in one schema would write to the same tables, so a change in dev would reach prod.

Patterns of your own, set as `catalog` and `schema`, aren't supported yet. A version 1 `mason.platform.yaml` with patterns that match a style is read as that style. Patterns that match none fail with [`MSN124`](../reference/rules/msn124.md), which names the closest style.

If your convention still doesn't fit, [open an issue on mason-core](https://github.com/nimblestax/mason-core/issues/new) with the catalog and schema names you use. Real names help decide what custom patterns must allow.
