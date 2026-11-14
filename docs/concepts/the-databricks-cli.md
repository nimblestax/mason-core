---
title: The Databricks CLI
description: Brickie brings its own pinned Databricks CLI, so every machine deploys with the same version.
---

Brickie deploys through the Databricks CLI, and it brings its own. Each Brickie release names one CLI version. The `databricks` on your PATH is never used, so your laptop and CI deploy the same project the same way, whichever CLI you have installed.

```console
$ brickie --version
brickie 0.1.0
Databricks CLI 1.23.0
```

## Where it comes from

The first time a command needs the CLI, Brickie downloads that version from Databricks' GitHub releases. It checks the archive against the checksum its release names. An archive that doesn't match is refused with [`BRK910`](../reference/rules/brk910.md), and nothing runs.

Brickie keeps the CLI in your cache folder, one folder per version, and reuses it after that:

| System | Folder |
| --- | --- |
| Linux | `~/.cache/brickie/databricks-cli/`, or under `$XDG_CACHE_HOME` |
| macOS | `~/Library/Caches/brickie/databricks-cli/` |
| Windows | `%LOCALAPPDATA%\brickie\databricks-cli\` |

Two projects on different Brickie versions each run their own CLI. Two runs that start at once download it once.

The download honours `HTTPS_PROXY` and `NO_PROXY`. If it fails, Brickie reports [`BRK912`](../reference/rules/brk912.md).

## Run it yourself

[`brickie databricks`](../reference/commands/databricks.md) runs the same CLI, with your arguments passed through, so you don't need a CLI of your own:

```console
$ brickie databricks auth describe
```

A `databricks` command you run yourself uses your own CLI, which can be a different version and behave differently.

## A machine that can't download it

On a machine with no route to GitHub, install the Databricks CLI yourself and point `BRICKIE_DATABRICKS_CLI` at it:

```console
$ export BRICKIE_DATABRICKS_CLI=/opt/databricks/databricks
```

Brickie reads its version first. A CLI older than the release supports is refused with [`BRK911`](../reference/rules/brk911.md), so an old CLI can't deploy your project differently.
