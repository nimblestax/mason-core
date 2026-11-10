---
title: Changelog
description: What changed in each release of Mason, newest first.
---

Every release of Mason, newest first. Each section is also that release's notes on GitHub.

Each pull request that changes what you see adds its line under Unreleased, so each release's section is built up by its pull requests. A release renames Unreleased to its version.

Mason follows [Semantic Versioning](https://semver.org). Before 1.0, a minor release, such as 0.2.0, may change config or commands in ways that need edits to your project, and its section here says what to change. A patch release, such as 0.2.1, never does.

## Unreleased

- Mason brings its own Databricks CLI, version 1.23.0, and never runs the `databricks` on your PATH. It downloads it the first time a command needs it, checks it against its checksum, and caches it. See [The Databricks CLI](concepts/the-databricks-cli.md).
  - `mason --version` prints Mason's version and the CLI version it runs.
  - `mason databricks <arguments>` runs that CLI, so you don't need one of your own.
  - `MASON_DATABRICKS_CLI` points Mason at a CLI you installed yourself, for a machine that can't download one.
  - New rules: MSN910 `databricks-cli-checksum-mismatch`, MSN911 `databricks-cli-unsupported`, MSN912 `databricks-cli-download-failed` and MSN913 `no-databricks-cli-for-platform`. MSN903 `databricks-cli-missing` now means `MASON_DATABRICKS_CLI` names a CLI Mason can't run.
- The workflows `mason init --ci github` writes no longer install the Databricks CLI.

**What to change:** delete the `databricks/setup-cli` step from `.github/workflows/mason-merge.yaml`. It does no harm, but Mason no longer uses that CLI.

## 0.3.0

- In `mason.platform.yaml`, test and prod use dev's `host` unless they set their own, so a project on one workspace sets `host` once. Every project now has a dev Environment with a `host`, checked by [`MSN122`](reference/rules/msn122.md).
- One Environment may set `default: true`, and commands that read use it when `--env` is left out. With none, dev is the default. Two defaults fail with [`MSN123`](reference/rules/msn123.md).
- `mason deploy` without `--env` says to add one, and exits 2. A deploy never uses the default Environment.
- Each Rule's reference page links to the Nimblestax Way principle behind it by that principle's current name. [`MSN201`](reference/rules/msn201.md) and [`MSN205`](reference/rules/msn205.md) now link to Code names tables logically; Mason resolves the environment. [`MSN116`](reference/rules/msn116.md) and [`MSN907`](reference/rules/msn907.md) link to No row disappears silently.

**What to change:** a project that passed `mason validate` on 0.2.0 can fail it on 0.3.0. Run `mason validate` and fix what it reports:

- MSN122: add `host` under `environments.dev`, set to dev's workspace URL. If your Environments have other names, rename the one you develop in to `dev`.

## 0.2.0

- `mason init` takes the project folder as an argument, `mason init sales-platform`, and creates it. With no folder it uses the current one. `mason init --project <folder>` is gone: write `mason init <folder>` instead. The other commands keep `--project`.
- `mason init` refuses a folder that already holds `mason.platform.yaml`, with [`MSN909`](reference/rules/msn909.md), and writes nothing. Before, it replaced the Platform Contract and every starter file.
- `mason init` asks where your tables live and offers three naming styles: `domain-catalogs` (`dev_sales.silver.orders`, the default), `layer-catalogs` (`dev_silver.sales.orders`) and `environment-catalogs` (`dev.sales_silver.orders`).
- `mason validate` checks that tables are read in build order: bronze, then silver, then gold.
  - MSN209 `cross-domain-read`: a gold model reads another domain's gold, or silver that domain hasn't exported. A domain exports silver with `export: true`. Gold in the shared domain, the domain called `shared`, is the one gold every domain may read.
  - MSN210 `read-against-build-order`: a gold model reads bronze.
  - MSN211 `stream-of-upsert-silver`: a gold model reads silver that has `keys` with `STREAM(...)`. Upserts change rows in place, so the stream fails after a change.
- Every Kind and every command has its own reference page, and the JSON output page describes each command's `--json` result.

**What to change:** replace `mason init --project <folder>` with `mason init <folder>` in any script. A project that passed `mason validate` on 0.1.0 can fail it on 0.2.0. Run `mason validate` and fix what it reports:

- MSN209: read silver the other domain has exported, or ask its owner to export it. To share a gold model, move it into the shared domain.
- MSN210: read the silver table of the same name, which the diagnostic gives.
- MSN211: read the table without `STREAM(...)`, as `FROM sales.silver.orders`. The gold model becomes a materialized view, which Databricks refreshes incrementally where it can.

## 0.1.0

The first release. Install it into your project with `uv add --dev mason-databricks`.

- `mason init` creates a working project, with GitHub Actions workflows.
- `mason validate` checks config and SQL with no workspace. A Model's dependencies come from its SQL, and anything Mason can't read, such as `IDENTIFIER(...)`, is an error rather than a guess.
- `mason compile` writes the generated code, or prints it for one Environment.
- `mason deploy` deploys to an Environment and refreshes its tables. When a refresh fails, it says why.
- `mason schema` prints any Kind's fields.
- A Source lands in bronze, and silver either appends it or upserts it by `keys` and `sequence_by`, with Type 1 or Type 2 history and `delete_when` for deletes.
- Seeds load small reference tables from CSV files in the repo.
- Expectations check silver rows, and rows that fail are kept in Quarantine.
- Every command has `--json` output, with rule IDs and fixed exit codes, and each rule has its own reference page.
