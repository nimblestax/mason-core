---
title: JSON output
description: The envelope every command prints with --json, its exit codes and its rule IDs.
generated: true
brickie_version: 0.1.0
redirects:
- json-output
---

Every `brickie` command but [`brickie databricks`](commands/databricks.md), which hands its arguments to the Databricks CLI, accepts `--json`. It prints one envelope on stdout and nothing else there. Logs, including the Databricks CLI's output, go to stderr.

```json
{
  "schema": "brickie.validate/1",
  "brickie_version": "0.1.0",
  "ok": false,
  "result": {},
  "diagnostics": [
    {
      "rule": "BRK201",
      "name": "unresolved-logical-name",
      "severity": "error",
      "file": "domains/sales/models/gold/fct_orders.sql",
      "line": null,
      "message": "sales.silver.nope isn't a table in this project.",
      "fix": "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
      "docs": "https://github.com/nimblestax/brickie-core/blob/main/docs/reference/json-output.md#rule-ids"
    }
  ]
}
```

## Envelope

The fields of the envelope, in the order they are printed.

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | The command and the version of its result, such as `brickie.validate/1`. A usage error that names no command uses `brickie.usage/1`. |
| `brickie_version` | string | The installed Brickie. |
| `ok` | boolean | Whether the command succeeded. |
| `result` | object | The command's own output, which its page describes. It is `{}` when the command fails. |
| `diagnostics` | array of object | Every problem found. |

## Diagnostics

Each diagnostic in `diagnostics` is one problem found.

| Field | Type | Meaning |
| --- | --- | --- |
| `rule` | string | The Rule's ID, such as `BRK201`. An ID never changes meaning. |
| `name` | string | The Rule's name, such as `unresolved-logical-name`. |
| `severity` | string | How serious it is. An `error` fails the command. A `warning` is reported and the command still succeeds. |
| `file` | string | The file it's in, from the project folder, or empty when none is. |
| `line` | integer or null | The line in `file`, or `null` when it doesn't apply. |
| `message` | string | What is wrong. |
| `fix` | string | What to change, as an instruction in words, not a patch Brickie applies. |
| `docs` | string | Where the Rule is explained. |

## Results

Each command's page describes its `result`.

- [`brickie init`](commands/init.md): Create a working project in a folder, by default the current one.
- [`brickie validate`](commands/validate.md): Check config and SQL references. With `--platform`, also check the workspace.
- [`brickie schema`](commands/schema.md): Print a Kind's fields from the installed Brickie. Needs no project.
- [`brickie compile`](commands/compile.md): Write generated code, or print it for one Environment.
- [`brickie deploy`](commands/deploy.md): Deploy to an Environment and refresh its tables.
- [`brickie skills update`](commands/skills.md#update): Refresh both copies of each Brickie Skill to this Brickie's version.

## Exit codes

Every command exits with one of these.

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## Rule IDs

Rule IDs are `BRK` plus three digits. An ID never changes meaning, and a retired ID is never reused. The [Rules index](rules/index.md) lists every Rule by series.

`brickie schema <unknown kind>` reports `BRK102` and exits 2, because the mistake is on the command line. Every `BRK1xx` and `BRK2xx` rule exits 1 when found in a project, and so does every `BRK3xx` rule, which `brickie validate --platform` finds in the workspace. A diagnostic with `severity` set to `warning`, such as `BRK129`, is reported and the command still exits 0.

When `brickie deploy` refreshes an Environment and a pipeline update fails, the diagnostic's `message` is the pipeline's own error, read from its event log: `BRK906`, `BRK907` or `BRK908`, each exiting 2. A pipeline retries a failed update once, so an error a retry can't fix is reported in about a minute. When no pipeline error can be read, Brickie reports `BRK904` with the Databricks CLI's last lines.
