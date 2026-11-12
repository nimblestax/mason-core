---
title: mason init
description: Create a working project in a folder, by default the current one.
generated: true
mason_version: 0.3.0
---

```console
$ mason init [<folder>] [OPTIONS]
```

## Arguments

| Argument | Meaning |
| --- | --- |
| `folder` | The folder to create the project in, made if missing. Its name is the project's name, except for an example, which keeps its own. |

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--ci` | `github` | `github` | CI provider to write files for. |
| `--host` | text | `https://your-workspace.cloud.databricks.com` | Workspace URL. |
| `--naming-style` | `domain-catalogs`, `layer-catalogs`, `environment-catalogs` |  | Where tables live. Asked at a terminal when left out; otherwise domain-catalogs. |
| `--skills` | `all`, `none` | `all` | Mason Skills to write for coding agents, into `.agents/skills/` and `.claude/skills/`. |
| `--example` | text |  | Write an example project with its sample data, such as `kettle`, instead of a new one. It keeps the Naming Style it ships with. |
| `--json` | Nothing |  | Print one JSON envelope. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `mason.init/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `project` | string | The folder the project was created in. |
| `naming_style` | string | The Naming Style written into its Platform Contract. |
| `catalogs` | array of string | The catalogs to create before deploying. |
| `schemas` | array of string | The schemas to create before deploying, as `catalog.schema`. |
| `skills` | array of string | The Mason Skill folders written. |
| `skills_left_alone` | array of string | The Mason Skill folders that already existed, which were left as they were. |
| `volumes` | array of string | The Volumes the Sources read in dev, as `catalog.schema.volume`, to create before deploying. |
| `example` | string or null | The example written, or `null` for a new project. |
| `uploads` | array of string | With `--example`, the commands that upload day 1's data to each Source's path in dev. |
