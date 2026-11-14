---
title: brickie validate
description: Check config and SQL references. With `--platform`, also check the workspace.
generated: true
brickie_version: 0.1.0
---

```console
$ brickie validate [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--platform` | Nothing |  | Also check, in the Environment's workspace, that the catalogs and schemas the project needs exist. |
| `--env` | text |  | The Environment whose workspace `--platform` checks. Defaults to the default Environment. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `brickie.validate/1`. When it succeeds, `result` is:

Empty: `validate` reports what it finds as diagnostics.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
