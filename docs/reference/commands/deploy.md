---
title: brickie deploy
description: Deploy to an Environment and refresh its tables.
generated: true
brickie_version: 0.1.0
---

```console
$ brickie deploy [OPTIONS]
```

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--env` | text |  | The Environment to deploy. Required: a deploy never uses the default Environment. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `brickie.deploy/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `env` | string | The Environment deployed and refreshed. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
