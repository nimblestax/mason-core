---
title: brickie schema
description: Print a Kind's fields from the installed Brickie. Needs no project.
generated: true
brickie_version: 0.1.0
---

```console
$ brickie schema <kind> [OPTIONS]
```

## Arguments

| Argument | Meaning |
| --- | --- |
| `kind` | The Kind to describe. |

## Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--json` | Nothing |  | Print one JSON envelope. |

## JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `brickie.schema/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | string | The Kind described. |
| `version` | integer | The newest version of the Kind this Brickie supports. |
| `json_schema` | object | The Kind's JSON Schema at that version. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
