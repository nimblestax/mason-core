---
title: Platform Contract
description: The shared facts about a project's platform.
generated: true
mason_version: 0.3.0
---

A file with `kind: platform`, at version 2. `mason schema platform` prints the same fields from the Mason you installed.

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `kind` | `platform` | yes |  | The Kind of this file. |
| `version` | `2` | yes |  | The schema version of this Kind. |
| `name` | string | yes |  | The project's name. |
| `environments` | map of name to object | yes |  | Settings per Environment. |
| `environments.<name>.host` | string | no | `null` | Workspace URL. Required on dev; test and prod use dev's unless they set their own. |
| `environments.<name>.default` | boolean | no | `false` | Whether commands that read use this Environment when `--env` is left out. At most one Environment sets it; with none, dev is the default. `mason deploy` always needs `--env`. |
| `environments.<name>.schedule` | object | no | `null` | When the Environment's Job runs on its own. Left out, it runs only on each deploy. |
| `environments.<name>.schedule.cron` | string | yes |  | A Quartz cron expression, such as `0 0 6 * * ?` for 6am every day. |
| `environments.<name>.schedule.timezone` | string | no | `UTC` | The time zone `cron` is read in, such as `Australia/Sydney`. |
| `environments.<name>.schedule.paused` | boolean | no | `null` | Whether the schedule is paused. Left out, it runs in prod and is paused everywhere else. |
| `naming` | object | yes |  | The Naming Style, and the model Layers. |
| `naming.style` | one of `domain-catalogs`, `layer-catalogs`, `environment-catalogs` | yes |  | Where tables live. In prod, `sales.silver.orders` is `prod_sales.silver.orders` under `domain-catalogs`, `prod_silver.sales.orders` under `layer-catalogs`, `prod.sales_silver.orders` under `environment-catalogs`. |
| `naming.layers` | object | yes |  | The model Layers. |
| `naming.layers.models` | list of string | yes |  | One or more model Layers, in any order. Each is a folder under `models/`. |
| `domains` | list of string | yes |  | The Domains, one folder each under `domains/`. |
