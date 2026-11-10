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
- `mason.platform.yaml` keeps the naming style by name, as `naming.style`, in version 2 of the `platform` Kind. Hand-edited `catalog` and `schema` patterns are no longer accepted. `mason init` writes version 2, with a comment that lists the three styles. See [Naming](concepts/naming.md).
  - A version 1 file still works when its patterns match a style, and Mason reads it as that style. Patterns that match none fail with [`MSN124`](reference/rules/msn124.md) `naming-patterns-not-supported`, which names the closest style.
  - The source layers are always `bronze` and `silver`. A version 1 file that names others fails with [`MSN125`](reference/rules/msn125.md) `source-layers-fixed`.
- Model layers have no order, and a gold model's folder is the only thing that sets its layer. See [Domains and layers](concepts/domains-and-layers.md).
  - A gold model can read any model layer in its own domain, in either direction. A loop of reads across model layers fails with [`MSN208`](reference/rules/msn208.md).
  - A model layer called `bronze` or `silver` fails with [`MSN126`](reference/rules/msn126.md) `model-layer-named-like-a-source-layer`.
  - A gold model's layer is always the first folder under `models/`. A file directly in `models/`, or in a folder that isn't a model layer, fails with [`MSN127`](reference/rules/msn127.md) `model-outside-a-layer`. Before, a file directly in `models/` went into the last model layer, and a folder that wasn't a model layer was skipped without a word.
  - Folders under `sources/`, `seeds/` and a model layer's folder are read at any depth, and only group files. Two files with one name in one domain's layer fail with [`MSN120`](reference/rules/msn120.md), naming both.
  - A domain can be a source system, such as `salesforce`, with gold in business domains that read its exported silver.
- Each Environment's Job waits only where one pipeline reads another's tables. A domain's gold waits for the ingest pipelines whose silver it reads, its own or another domain's exported silver, and for the shared domain's gold if it reads it. A failed pipeline skips only what reads from it, so an unrelated domain still refreshes. Before, a domain's gold always waited for its own ingest and never for another domain's.
- Pipeline and Job names carry the Environment, such as `kettle_dev_sales_ingest` and `kettle_dev_refresh`, so dev, test and prod can share one workspace. Before, a second Environment in the same workspace failed to deploy, because Databricks refuses a second pipeline with the same name. The next deploy renames each Environment's pipelines and Job in place.
- An Environment can refresh on a schedule, set as `schedule` in `mason.platform.yaml`. A schedule runs in prod and is paused in every other Environment unless it sets `paused: false`. See [Schedule refreshes](guides/schedule-refreshes.md).

**What to change:** delete the `databricks/setup-cli` step from `.github/workflows/mason-merge.yaml`. It does no harm, but Mason no longer uses that CLI.

A version 1 `mason.platform.yaml` whose patterns match a style needs no change yet. To move it to version 2, set `version: 2`, replace `catalog` and `schema` under `naming` with `style`, and delete `naming.layers.sources`. Use the style your patterns match, so no table moves: `{env}_{domain}` / `{layer}` is `domain-catalogs`, `{env}_{layer}` / `{domain}` is `layer-catalogs`, and `{env}` / `{domain}_{layer}` is `environment-catalogs`. Then point the schema comment on the first line at `.mason/schemas/platform.v2.json`, and copy that file from a project `mason init` creates, so your editor checks the new fields. If you see `MSN124`, your patterns match no style: see [When none of these fit](concepts/naming.md#when-none-of-these-fit) before you pick one, because a new style moves every table.

A project that passed `mason validate` before can also fail it on this:

- MSN127: move each gold model that sits directly in `domains/<domain>/models/` into `domains/<domain>/models/gold/`, or into the folder of the model layer it belongs to. A model moved into the last model layer, where it used to land, keeps its table.

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
