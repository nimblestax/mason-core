---
title: The Databricks CLI
description: Mason brings its own pinned Databricks CLI, so every machine deploys with the same version.
---

Mason deploys through the Databricks CLI, and it brings its own. Each Mason release names one CLI version. The `databricks` on your PATH is never used, so your laptop and CI deploy the same project the same way, whichever CLI you have installed.

```console
$ mason --version
mason 0.3.0
Databricks CLI 1.23.0
```

## Where it comes from

The first time a command needs the CLI, Mason downloads that version from Databricks' GitHub releases. It checks the archive against the checksum its release names. An archive that doesn't match is refused with [`MSN910`](../reference/rules/msn910.md), and nothing runs.

Mason keeps the CLI in your cache folder, one folder per version, and reuses it after that:

| System | Folder |
| --- | --- |
| Linux | `~/.cache/mason/databricks-cli/`, or under `$XDG_CACHE_HOME` |
| macOS | `~/Library/Caches/mason/databricks-cli/` |
| Windows | `%LOCALAPPDATA%\mason\databricks-cli\` |

Two projects on different Mason versions each run their own CLI. Two runs that start at once download it once.

The download honours `HTTPS_PROXY` and `NO_PROXY`. If it fails, Mason reports [`MSN912`](../reference/rules/msn912.md).

## Run it yourself

[`mason databricks`](../reference/commands/databricks.md) runs the same CLI, with your arguments passed through, so you don't need a CLI of your own:

```console
$ mason databricks auth describe
```

A `databricks` command you run yourself uses your own CLI, which can be a different version and behave differently.

## A machine that can't download it

On a machine with no route to GitHub, install the Databricks CLI yourself and point `MASON_DATABRICKS_CLI` at it:

```console
$ export MASON_DATABRICKS_CLI=/opt/databricks/databricks
```

Mason reads its version first. A CLI older than the release supports is refused with [`MSN911`](../reference/rules/msn911.md), so an old CLI can't deploy your project differently.
