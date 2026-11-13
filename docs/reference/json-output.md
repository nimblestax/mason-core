---
title: JSON output
description: The envelope every command prints with --json, its exit codes and its rule IDs.
generated: true
mason_version: 0.3.0
redirects:
- json-output
---

Every `mason` command but [`mason databricks`](commands/databricks.md), which hands its arguments to the Databricks CLI, accepts `--json`. It prints one envelope on stdout and nothing else there. Logs, including the Databricks CLI's output, go to stderr.

```json
{
  "schema": "mason.validate/1",
  "mason_version": "0.3.0",
  "ok": false,
  "result": {},
  "diagnostics": [
    {
      "rule": "MSN201",
      "name": "unresolved-logical-name",
      "severity": "error",
      "file": "domains/sales/models/gold/fct_orders.sql",
      "line": null,
      "message": "sales.silver.nope isn't a table in this project.",
      "fix": "Declare a Source, Seed or Gold Model with this name, or correct the Logical Name.",
      "docs": "https://github.com/nimblestax/mason-core/blob/main/docs/reference/json-output.md#rule-ids"
    }
  ]
}
```

## Envelope

The fields of the envelope, in the order they are printed.

| Field | Type | Meaning |
| --- | --- | --- |
| `schema` | string | The command and the version of its result, such as `mason.validate/1`. A usage error that names no command uses `mason.usage/1`. |
| `mason_version` | string | The installed Mason. |
| `ok` | boolean | Whether the command succeeded. |
| `result` | object | The command's own output, which its page describes. It is `{}` when the command fails. |
| `diagnostics` | array of object | Every problem found. |

## Diagnostics

Each diagnostic in `diagnostics` is one problem found.

| Field | Type | Meaning |
| --- | --- | --- |
| `rule` | string | The Rule's ID, such as `MSN201`. An ID never changes meaning. |
| `name` | string | The Rule's name, such as `unresolved-logical-name`. |
| `severity` | string | How serious it is. An `error` fails the command. A `warning` is reported and the command still succeeds. |
| `file` | string | The file it's in, from the project folder, or empty when none is. |
| `line` | integer or null | The line in `file`, or `null` when it doesn't apply. |
| `message` | string | What is wrong. |
| `fix` | string | What to change, as an instruction in words, not a patch Mason applies. |
| `docs` | string | Where the Rule is explained. |

## Results

Each command's page describes its `result`.

- [`mason init`](commands/init.md): Create a working project in a folder, by default the current one.
- [`mason validate`](commands/validate.md): Check config and SQL references. With `--platform`, also check the workspace.
- [`mason schema`](commands/schema.md): Print a Kind's fields from the installed Mason. Needs no project.
- [`mason compile`](commands/compile.md): Write generated code, or print it for one Environment.
- [`mason deploy`](commands/deploy.md): Deploy to an Environment and refresh its tables.
- [`mason skills update`](commands/skills.md#update): Refresh both copies of each Mason Skill to this Mason's version.

## Exit codes

Every command exits with one of these.

| Code | Meaning |
| --- | --- |
| 0 | Clean |
| 1 | Rule failures: the project needs a change |
| 2 | Usage or environment error: the command line or the machine needs a change |

## Rule IDs

Rule IDs are `MSN` plus three digits. An ID never changes meaning, and a retired ID is never reused. The [Rules index](rules/index.md) lists every Rule by series.

`mason schema <unknown kind>` reports `MSN102` and exits 2, because the mistake is on the command line. Every `MSN1xx` and `MSN2xx` rule exits 1 when found in a project, and so does every `MSN3xx` rule, which `mason validate --platform` finds in the workspace. A diagnostic with `severity` set to `warning`, such as `MSN129`, is reported and the command still exits 0.

When `mason deploy` refreshes an Environment and a pipeline update fails, the diagnostic's `message` is the pipeline's own error, read from its event log: `MSN906`, `MSN907` or `MSN908`, each exiting 2. A pipeline retries a failed update once, so an error a retry can't fix is reported in about a minute. When no pipeline error can be read, Mason reports `MSN904` with the Databricks CLI's last lines.
