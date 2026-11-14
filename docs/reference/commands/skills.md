---
title: brickie skills
description: Keep the Brickie Skills in this project.
generated: true
brickie_version: 0.1.0
---

## update

Refresh both copies of each Brickie Skill to this Brickie's version.

```console
$ brickie skills update [OPTIONS]
```

### Options

| Option | Takes | Default | Meaning |
| --- | --- | --- | --- |
| `--force` | Nothing |  | Replace skills edited since Brickie wrote them. |
| `--project` | path | `.` | The project folder. |
| `--json` | Nothing |  | Print one JSON envelope. |

### JSON result

With `--json`, it prints the [envelope](../json-output.md) with `schema` set to `brickie.skills.update/1`. When it succeeds, `result` is:

| Field | Type | Meaning |
| --- | --- | --- |
| `skills` | array of string | The Brickie Skill folders written. A skill already up to date isn't listed. |

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |
