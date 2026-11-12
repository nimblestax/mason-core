---
title: Environments
description: How Mason knows an environment by its role rather than its name, how to add stages of your own, and what one shared workspace means.
---

An environment is a long-lived place your pipelines deploy to, such as dev, test or prod. You name your environments, and you tell Mason what two of them are for with `role`.

```yaml
environments:
  dev:
    host: https://kettle.cloud.databricks.com
    role: development
  test: {}
  sit: {}
  prod:
    role: production
```

`mason init` writes `dev` with `role: development`. Add the others as you need them.

## Roles

Mason never reads meaning into a name. An environment called `prod` with no role is an ordinary stage, and one called `prd` with `role: production` is the production environment.

- **The development environment** is the one you work in. A project has exactly one. Commands that read, such as `mason validate --platform` and `mason compile --env`, use it when you leave out `--env`, unless another environment sets `default: true`. Every environment without a `host` uses its `host`.
- **The production environment** is the one kept isolated. A project has at most one, so a project with only a development environment is fine. A schedule runs in it and is paused everywhere else, unless the schedule says otherwise. See [Schedule refreshes](../guides/schedule-refreshes.md).

Each role is held by a different environment. One environment holding both would put work in progress beside approved production tables.

`mason validate` fails when no environment has `role: development`:

```text
MSN130 mason.platform.yaml: No Environment sets `role: development`, and every project has one Development Environment.
  Fix: Add `role: development` to the Environment people develop in, such as `dev`.
```

Two environments with one role fail with [`MSN131`](../reference/rules/msn131.md).

## Names

An environment's name is what appears in its catalogs, so under `domain-catalogs`, `sales.silver.orders` is `prd_sales.silver.orders` in an environment called `prd`. Mason writes catalog names into SQL unquoted, so a name must be letters, digits and underscores, and can't start with a digit. A name like `prd-1` fails with [`MSN132`](../reference/rules/msn132.md). See [Naming](naming.md) for how each style builds the catalog.

## Stages

Any environment without a role is a stage, such as `test`, `sit` or `uat`. Add as many as you need. Each one gets its own catalogs, its own settings in the build package and its own Job, and `mason deploy --env sit` deploys to it. Mason never needs to know their order: your CI runs them in the order you choose.

## One shared workspace

Environments can share a workspace, under every naming style. The environment's name is part of every catalog name, so environments sharing a workspace never share a table.

On one workspace, what keeps the production environment apart is each environment's CI identity and the grants on its catalogs. Mason doesn't check either, so give each environment its own CI identity, and grant on each environment's catalogs separately. When you can, give the production environment its own `host`, so a workspace boundary keeps it apart too.

## Upgrading a version 1 file

A version 1 `mason.platform.yaml` has no roles. Mason reads `dev` as the development environment and `prod` as the production environment, so it needs no change.
