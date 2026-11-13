---
title: Rules
description: Every Rule Mason checks, by series, with what each one checks.
generated: true
mason_version: 0.3.0
---

A Rule's ID is `MSN` plus three digits, and its first digit is its series. Each Rule's page says what it checks, why, an example that fails and the fix.

## `MSN1xx` Config files

| Rule | Name | What it checks |
| --- | --- | --- |
| [`MSN101`](msn101.md) | `missing-kind` | A config file has no `kind`. |
| [`MSN102`](msn102.md) | `unknown-kind` | A `kind` isn't one Mason knows. |
| [`MSN103`](msn103.md) | `missing-version` | A config file has no `version`. |
| [`MSN104`](msn104.md) | `unknown-version` | This Mason doesn't support that `version`. |
| [`MSN105`](msn105.md) | `wrong-kind` | A file's `kind` doesn't belong in its location. |
| [`MSN106`](msn106.md) | `invalid-field` | A field doesn't match its Kind's schema. |
| [`MSN107`](msn107.md) | `unreadable-config` | A config file is missing, isn't valid YAML or isn't a mapping, or a Seed's file isn't valid CSV. |
| [`MSN108`](msn108.md) | `sql-without-config` | A SQL file has no config file beside it. |
| [`MSN109`](msn109.md) | `missing-sql-file` | A model names a SQL file that doesn't exist. |
| [`MSN110`](msn110.md) | `keys-without-sequence-by` | A Source's `silver` block has `keys` but no `sequence_by`. |
| [`MSN111`](msn111.md) | `upsert-field-without-keys` | A Source's `silver` block has `sequence_by`, `scd` or `delete_when` but no `keys`. |
| [`MSN112`](msn112.md) | `missing-seed-file` | A Seed's `file` doesn't exist beside it. |
| [`MSN113`](msn113.md) | `seed-header-mismatch` | The first line of a Seed's file doesn't name each declared column once. |
| [`MSN114`](msn114.md) | `seed-row-mismatch` | A row of a Seed's file has the wrong number of values, or a value that doesn't fit its column's type. |
| [`MSN115`](msn115.md) | `unsupported-seed-type` | A Seed's column has a type Mason can't check values against. |
| [`MSN116`](msn116.md) | `invalid-expectation` | An Expectation's `expect` isn't one SQL condition on one row: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`MSN117`](msn117.md) | `invalid-name` | A config file's name isn't an identifier, so the table named after it can't be written in SQL: it must hold only letters, digits and underscores, and not start with a digit. |
| [`MSN118`](msn118.md) | `invalid-delete-when` | A Source's `silver.delete_when` isn't one SQL condition on one row, for the same reasons as `MSN116`. |
| [`MSN119`](msn119.md) | `invalid-sequence-by` | A Source's `silver.sequence_by` isn't one SQL expression on one row, such as `updated_at` or `struct(updated_at, seq)`: it doesn't parse, or it holds a query, an aggregate, a window function, a comment or an alias. |
| [`MSN120`](msn120.md) | `duplicate-config-file` | Two config files share a name in one Domain's Layer: in one folder, such as `orders.yaml` and `orders.yml`, or in two folders, such as `sources/erp/orders.yaml` and `sources/crm/orders.yaml`. Mason reads either ending, and writes `.yaml`. |
| [`MSN121`](msn121.md) | `unlisted-domain-folder` | A folder under `domains/` isn't listed in `domains` in `mason.platform.yaml`, in the same case, so nothing in it is validated or deployed. |
| [`MSN122`](msn122.md) | `dev-host-missing` | `mason.platform.yaml` has no `host` on the Development Environment. In a version 1 file, which knows Environments by name, it has no `host` on `dev`. |
| [`MSN123`](msn123.md) | `two-default-environments` | More than one Environment in `mason.platform.yaml` sets `default: true`. |
| [`MSN124`](msn124.md) | `naming-patterns-not-supported` | `mason.platform.yaml` sets `catalog` and `schema` patterns that aren't a Naming Style, or sets any patterns at version 2, which takes only `naming.style`. |
| [`MSN125`](msn125.md) | `source-layers-fixed` | A version 1 `mason.platform.yaml` lists source Layers other than `[bronze, silver]`. |
| [`MSN126`](msn126.md) | `model-layer-named-like-a-source-layer` | A model Layer in `naming.layers.models` is called `bronze` or `silver`, in any case. |
| [`MSN127`](msn127.md) | `model-outside-a-layer` | A file sits directly in a Domain's `models/` folder, or in a first folder under it that isn't a model Layer in `naming.layers.models`. |
| [`MSN129`](msn129.md) | `skill-version-drift` | A Mason Skill in `.agents/skills/` or `.claude/skills/` was written by another version of Mason than the one installed. |
| [`MSN130`](msn130.md) | `no-development-environment` | No Environment in `mason.platform.yaml` sets `role: development`. |
| [`MSN131`](msn131.md) | `two-environments-with-one-role` | More than one Environment in `mason.platform.yaml` sets the same `role`. |
| [`MSN132`](msn132.md) | `environment-name-not-an-identifier` | An Environment's name in `mason.platform.yaml` isn't an identifier: letters, digits and underscores, starting with a letter or underscore. |

## `MSN2xx` SQL and reads between tables

| Rule | Name | What it checks |
| --- | --- | --- |
| [`MSN201`](msn201.md) | `unresolved-logical-name` | SQL reads a table that isn't in the project. |
| [`MSN202`](msn202.md) | `duplicate-table` | A Seed and a Source in one Domain share a name, so they would be one table. |
| [`MSN203`](msn203.md) | `unparseable-sql` | A Gold Model's SQL doesn't parse as one Databricks SQL query. |
| [`MSN204`](msn204.md) | `computed-table-name` | SQL builds a table name when it runs, such as `IDENTIFIER(...)`, so Mason can't see what it reads. |
| [`MSN205`](msn205.md) | `real-table-name` | SQL reads a real table name, which names one Environment, instead of its Logical Name. |
| [`MSN206`](msn206.md) | `file-read` | A Gold Model reads files or external data, such as `read_files(...)` or ``parquet.`/path` ``, instead of a table. |
| [`MSN207`](msn207.md) | `raw-string-placeholder` | A raw string in a Gold Model's SQL, such as `r'${env}'`, holds `${`. |
| [`MSN208`](msn208.md) | `model-cycle` | Gold Models read themselves, or each other in a loop, so none of them can run first. |
| [`MSN209`](msn209.md) | `cross-domain-read` | A Gold Model reads another Domain's gold, or silver that Domain hasn't Exported. |
| [`MSN210`](msn210.md) | `read-against-build-order` | A Gold Model reads bronze. |
| [`MSN211`](msn211.md) | `stream-of-upsert-silver` | A Gold Model reads silver that has `keys` with `STREAM(...)`. |
| [`MSN212`](msn212.md) | `stream-of-materialized-view` | A Gold Model reads a Seed, or a Gold Model that doesn't stream, with `STREAM(...)`. |

## `MSN3xx` The workspace a project deploys to

| Rule | Name | What it checks |
| --- | --- | --- |
| [`MSN301`](msn301.md) | `missing-catalog` | With `--platform`, a catalog the project's tables need isn't in the Environment's workspace, or the identity Mason signs in as can't see it. |
| [`MSN302`](msn302.md) | `missing-schema` | With `--platform`, a schema the project's tables need isn't in its catalog in the Environment's workspace, or the identity Mason signs in as can't see it. |

## `MSN9xx` The command line and running against Databricks

| Rule | Name | What it checks |
| --- | --- | --- |
| [`MSN901`](msn901.md) | `usage-error` | The command line is wrong. |
| [`MSN902`](msn902.md) | `unknown-environment` | `--env` isn't an Environment in the project. |
| [`MSN903`](msn903.md) | `databricks-cli-missing` | `MASON_DATABRICKS_CLI` names a Databricks CLI that Mason can't run. |
| [`MSN904`](msn904.md) | `databricks-command-failed` | A Databricks CLI command failed. |
| [`MSN905`](msn905.md) | `unexpected-error` | Mason stopped on something it didn't expect, with a traceback on stderr. |
| [`MSN906`](msn906.md) | `pipeline-column-not-found` | The refresh failed because a pipeline names a column its table doesn't have, often an Expectation on a column bronze doesn't have yet. |
| [`MSN907`](msn907.md) | `expectation-failed` | The refresh failed because a row broke an Expectation whose `action` is `fail`. |
| [`MSN908`](msn908.md) | `pipeline-failed` | The refresh failed with another pipeline error. The message is the pipeline's own. |
| [`MSN909`](msn909.md) | `project-already-exists` | `mason init` was run in a folder that already holds `mason.platform.yaml`. |
| [`MSN910`](msn910.md) | `databricks-cli-checksum-mismatch` | The Databricks CLI Mason downloaded doesn't match the checksum its release names. |
| [`MSN911`](msn911.md) | `databricks-cli-unsupported` | `MASON_DATABRICKS_CLI` names a Databricks CLI older than this Mason supports. |
| [`MSN912`](msn912.md) | `databricks-cli-download-failed` | Mason couldn't download its Databricks CLI. |
| [`MSN913`](msn913.md) | `no-databricks-cli-for-platform` | Databricks publishes no CLI for this operating system and architecture. |
| [`MSN914`](msn914.md) | `skills-folder-ignored` | `mason init` wrote Mason Skills into a folder Git ignores, such as `.claude/`. |
| [`MSN915`](msn915.md) | `skill-edited` | `mason skills update` found a Mason Skill edited since Mason wrote it. |
| [`MSN916`](msn916.md) | `unknown-example` | `mason init --example` names an example Mason doesn't ship. |
