---
title: Changelog
description: What changed in each release of Brickie, newest first.
---

Every release of Brickie, newest first. Each section is also that release's notes on GitHub.

Each pull request that changes what you see adds its line under Unreleased, so each release's section is built up by its pull requests. A release renames Unreleased to its version.

Brickie follows [Semantic Versioning](https://semver.org). Before 1.0, a minor release, such as 0.2.0, may change config or commands in ways that need edits to your project, and its section here says what to change. A patch release, such as 0.2.1, never does.

## Unreleased

## 0.1.0

The first release. Install it into your project with `uv add --dev brickie-core`.

- [`brickie init`](reference/commands/init.md) creates a project folder and asks where your tables live: `domain-catalogs` (`dev_sales.silver.orders`, the default), `layer-catalogs` (`dev_silver.sales.orders`) or `environment-catalogs` (`dev.sales_silver.orders`). `brickie.platform.yaml` keeps that choice as `naming.style`. See [Naming](concepts/naming.md).
  - It refuses a folder that already holds `brickie.platform.yaml`, with [`BRK909`](reference/rules/brk909.md), and writes nothing.
  - `--ci github` adds GitHub Actions workflows, `.github/workflows/brickie-pull-request.yaml` and `.github/workflows/brickie-merge.yaml`. They install `brickie-core` at the version `BRICKIE_SPEC` names.
  - It lists the Volumes the project's sources read in dev, with the catalogs and schemas to create.
  - `--example kettle` writes Kettle, the fictional tea shop every docs page draws its examples from, with two days of sample data and the commands that upload day 1.
- Environments are named freely and carry a role: `role: development` on exactly one, and `role: production` on at most one. Any other environment is a stage. Commands that read default to the development environment, and an environment without a `host` uses its host. See [Environments](concepts/environments.md).
- [`brickie validate`](reference/commands/validate.md) checks config and SQL with no workspace. A gold model's dependencies come from its SQL, and anything Brickie can't read, such as `IDENTIFIER(...)`, is an error rather than a guess.
  - Tables are read in build order. A gold model reads silver, a gold model in its own domain, another domain's exported silver, or gold in the shared domain. See [Domains and layers](concepts/domains-and-layers.md).
  - Model layers have no order, and a gold model's folder sets its layer. A loop of reads across model layers fails.
  - `--platform` signs in to an environment's workspace and checks that the catalogs and schemas the project needs are there.
  - It warns when a skill was written by another Brickie version.
- [`brickie compile`](reference/commands/compile.md) writes the generated code, or prints it for one environment. A gold model that reads `STREAM(...)` compiles to a streaming table, and any other gold model to a materialized view. See [How Brickie reads a gold model's SQL](concepts/how-brickie-reads-a-gold-models-sql.md).
- [`brickie deploy`](reference/commands/deploy.md) deploys to the environment `--env` names and refreshes its tables. When a refresh fails, it says why. See [Recover from a failed refresh](guides/recover-from-a-failed-refresh.md).
  - Each environment has one Job, named for it, such as `kettle_dev_refresh`. It waits only where one pipeline reads another's tables, so a failed pipeline skips only what reads from it.
  - An environment can refresh on a schedule. A schedule runs in the production environment and is paused elsewhere. See [Schedule refreshes](guides/schedule-refreshes.md).
- [`brickie schema`](reference/commands/schema.md) prints any Kind's fields.
- A source lands in bronze, and silver either appends it or upserts it by `keys` and `sequence_by`, with Type 1 or Type 2 history and `delete_when` for deletes.
- Seeds load small reference tables from CSV files in the repo.
- Expectations check silver rows, and rows that fail are kept in quarantine. See [Expectations](concepts/expectations.md).
- Brickie brings its own Databricks CLI, version 1.23.0, and never runs the `databricks` on your PATH. [`brickie databricks`](reference/commands/databricks.md) runs it, and `BRICKIE_DATABRICKS_CLI` points Brickie at one you installed yourself. See [The Databricks CLI](concepts/the-databricks-cli.md).
- `brickie init` writes Brickie skills for coding agents, `brickie-add-source` and `brickie-add-model`, into `.agents/skills/` and `.claude/skills/`. [`brickie skills update`](reference/commands/skills.md#update) refreshes them. See [Brickie skills](concepts/brickie-skills.md).
- Every command but `brickie databricks` has `--json` output, with Rule IDs and fixed exit codes. See [JSON output](reference/json-output.md).
- Every Rule has its own reference page, listed in the [Rules index](reference/rules/index.md).
