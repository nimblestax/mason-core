---
title: Rules
description: Every Rule Brickie checks, by series, with what each one checks.
generated: true
brickie_version: 0.1.0
---

A Rule's ID is `BRK` plus three digits, and its first digit is its series. Each Rule's page says what it checks, why, an example that fails and the fix.

## `BRK1xx` Config files

| Rule | Name | What it checks |
| --- | --- | --- |
| [`BRK101`](brk101.md) | `missing-kind` | A config file has no `kind`. |
| [`BRK102`](brk102.md) | `unknown-kind` | A `kind` isn't one Brickie knows. |
| [`BRK103`](brk103.md) | `missing-version` | A config file has no `version`. |
| [`BRK104`](brk104.md) | `unknown-version` | This Brickie doesn't support that `version`. |
| [`BRK105`](brk105.md) | `wrong-kind` | A file's `kind` doesn't belong in its location. |
| [`BRK106`](brk106.md) | `invalid-field` | A field doesn't match its Kind's schema. |
| [`BRK107`](brk107.md) | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file isn't valid CSV. |
| [`BRK108`](brk108.md) | `sql-without-config` | A SQL file has no config file beside it. |
| [`BRK109`](brk109.md) | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| [`BRK110`](brk110.md) | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| [`BRK111`](brk111.md) | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| [`BRK112`](brk112.md) | `missing-seed-file` | A Seed's `file` doesn't exist beside it. |
| [`BRK113`](brk113.md) | `seed-header-mismatch` | The first line of a Seed's file doesn't name each declared column once. |
| [`BRK114`](brk114.md) | `seed-row-mismatch` | A row of a Seed's file has the wrong number of values, or a value that doesn't fit its column's type. |
| [`BRK115`](brk115.md) | `unsupported-seed-type` | A Seed's column has a type Brickie can't check values against. |
| [`BRK116`](brk116.md) | `invalid-expectation` | An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`BRK117`](brk117.md) | `invalid-name` | A config file's name isn't an identifier, so the table named after it can't be written in SQL: it must hold only letters, digits and underscores, and not start with a digit. |
| [`BRK118`](brk118.md) | `invalid-delete-when` | A Source's `silver.delete_when` isn't one SQL condition on one row, for the same reasons as `BRK116`. |
| [`BRK119`](brk119.md) | `invalid-sequence-by` | A Source's `silver.sequence_by` isn't one SQL expression on one row, such as `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`BRK120`](brk120.md) | `duplicate-config-file` | Two config files share a name in one Domain's Layer: in one folder, such as `orders.yaml` and `orders.yml`, or in two folders, such as `sources/erp/orders.yaml` and `sources/crm/orders.yaml`. Brickie reads either ending, and writes `.yaml`. |
| [`BRK121`](brk121.md) | `unlisted-domain-folder` | A folder under `domains/` isn't listed in `domains` in `brickie.platform.yaml`, in the same case, so nothing in it is validated or deployed. |
| [`BRK122`](brk122.md) | `dev-host-missing` | `brickie.platform.yaml` has no `host` on the Development Environment. In a version 1 file, which knows Environments by name, it has no `host` on `dev`. |
| [`BRK123`](brk123.md) | `two-default-environments` | More than one Environment in `brickie.platform.yaml` sets `default: true`. |
| [`BRK124`](brk124.md) | `naming-patterns-not-supported` | `brickie.platform.yaml` sets `catalog` and `schema` patterns that aren't a Naming Style, or sets any patterns at version 2, which takes only `naming.style`. |
| [`BRK125`](brk125.md) | `source-layers-fixed` | A version 1 `brickie.platform.yaml` lists source Layers other than `[bronze, silver]`. |
| [`BRK126`](brk126.md) | `model-layer-named-like-a-source-layer` | A model Layer in `naming.layers.models` is called `bronze` or `silver`, in any case. |
| [`BRK127`](brk127.md) | `model-outside-a-layer` | A file sits directly in a Domain's `models/` folder, or in a first folder under it that isn't a model Layer in `naming.layers.models`. |
| [`BRK129`](brk129.md) | `skill-version-drift` | A Brickie Skill in `.agents/skills/` or `.claude/skills/` was written by another version of Brickie than the one installed. |
| [`BRK130`](brk130.md) | `no-development-environment` | No Environment in `brickie.platform.yaml` sets `role: development`. |
| [`BRK131`](brk131.md) | `two-environments-with-one-role` | More than one Environment in `brickie.platform.yaml` sets the same `role`. |
| [`BRK132`](brk132.md) | `environment-name-not-an-identifier` | An Environment's name in `brickie.platform.yaml` isn't an identifier: letters, digits and underscores, starting with a letter or underscore. |

## `BRK2xx` SQL and reads between tables

| Rule | Name | What it checks |
| --- | --- | --- |
| [`BRK201`](brk201.md) | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| [`BRK202`](brk202.md) | `duplicate-table` | A Seed and a Source in one Domain share a name, so they would be one table. |
| [`BRK203`](brk203.md) | `unparseable-sql` | A Gold Model's SQL doesn't parse as one Databricks SQL query. |
| [`BRK204`](brk204.md) | `computed-table-name` | SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Brickie can't see what it reads. |
| [`BRK205`](brk205.md) | `real-table-name` | SQL reads a real table name, which names one Environment, instead of its Logical Name. |
| [`BRK206`](brk206.md) | `file-read` | A Gold Model reads files or external data, such as `read_files(...)` or ``parquet.`/path` ``, instead of a table. |
| [`BRK207`](brk207.md) | `raw-string-placeholder` | A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`. |
| [`BRK208`](brk208.md) | `model-cycle` | Gold Models read themselves, or each other in a loop, so none of them can run first. |
| [`BRK209`](brk209.md) | `cross-domain-read` | A Gold Model reads another Domain's gold, or silver that Domain hasn't Exported. |
| [`BRK210`](brk210.md) | `read-against-build-order` | A Gold Model reads bronze. |
| [`BRK211`](brk211.md) | `stream-of-upsert-silver` | A Gold Model reads silver that has `keys` with `STREAM(...)`. |
| [`BRK212`](brk212.md) | `stream-of-materialized-view` | A Gold Model reads a Seed, or a Gold Model that doesn't stream, with `STREAM(...)`. |

## `BRK3xx` The workspace a project deploys to

| Rule | Name | What it checks |
| --- | --- | --- |
| [`BRK301`](brk301.md) | `missing-catalog` | With `--platform`, a catalog the project's tables need isn't in the Environment's workspace, or the identity Brickie signs in as can't see it. |
| [`BRK302`](brk302.md) | `missing-schema` | With `--platform`, a schema the project's tables need isn't in its catalog in the Environment's workspace, or the identity Brickie signs in as can't see it. |

## `BRK9xx` The command line and running against Databricks

| Rule | Name | What it checks |
| --- | --- | --- |
| [`BRK901`](brk901.md) | `usage-error` | The command line is wrong. |
| [`BRK902`](brk902.md) | `unknown-environment` | `--env` isn't an Environment in the project. |
| [`BRK903`](brk903.md) | `databricks-cli-missing` | `BRICKIE_DATABRICKS_CLI` names a Databricks CLI that Brickie can't run. |
| [`BRK904`](brk904.md) | `databricks-command-failed` | A Databricks CLI command failed. |
| [`BRK905`](brk905.md) | `unexpected-error` | Brickie stopped on something it didn't expect, with a traceback on stderr. |
| [`BRK906`](brk906.md) | `pipeline-column-not-found` | The refresh failed because a pipeline names a column its table doesn't have, often an Expectation on a column bronze doesn't have yet. |
| [`BRK907`](brk907.md) | `expectation-failed` | The refresh failed because a row broke an Expectation whose `action` is `fail`. |
| [`BRK908`](brk908.md) | `pipeline-failed` | The refresh failed with another pipeline error. The message is the pipeline's own. |
| [`BRK909`](brk909.md) | `project-already-exists` | `brickie init` was run in a folder that already holds `brickie.platform.yaml`. |
| [`BRK910`](brk910.md) | `databricks-cli-checksum-mismatch` | The Databricks CLI Brickie downloaded doesn't match the checksum its release names. |
| [`BRK911`](brk911.md) | `databricks-cli-unsupported` | `BRICKIE_DATABRICKS_CLI` names a Databricks CLI older than this Brickie supports. |
| [`BRK912`](brk912.md) | `databricks-cli-download-failed` | Brickie couldn't download its Databricks CLI. |
| [`BRK913`](brk913.md) | `no-databricks-cli-for-platform` | Databricks publishes no CLI for this operating system and architecture. |
| [`BRK914`](brk914.md) | `skills-folder-ignored` | `brickie init` wrote Brickie Skills into a folder Git ignores, such as `.claude/`. |
| [`BRK915`](brk915.md) | `skill-edited` | `brickie skills update` found a Brickie Skill edited since Brickie wrote it. |
| [`BRK916`](brk916.md) | `unknown-example` | `brickie init --example` names an example Brickie doesn't ship. |
