---
title: Expectations
description: The row-level rules a source's silver is checked against, which rows they check, and where failing rows go.
---

An expectation is a rule on one row of a source's silver table. A row meets it only when its `expect` condition is true. False or NULL is a failure.

```yaml
silver:
  keys: [account_id]
  sequence_by: ts
  delete_when: op = 'D'
  expectations:
    - name: has_email
      expect: email IS NOT NULL
```

Each rule has an `action`, which says what happens to a row that fails it:

| Action | What happens to a failing row |
| --- | --- |
| `quarantine` (the default) | It stays out of silver and goes to the source's quarantine table, `<source>_quarantine`, with the names of the rules it failed in `_quarantine_reason`. |
| `warn` | It reaches silver, and the failure is counted in the table's metrics. |
| `fail` | The update stops. |

## Which rows are checked

On an append source, every row is checked.

On an upsert source, which has `keys`, every change is checked, except a delete. A row where `delete_when` is true skips every expectation. It always reaches silver, where it deletes its key, and it never goes to quarantine. A delete often carries only its key, so a rule on any other column would fail it. If that sent it to quarantine, silver would keep a row the source had deleted, and nothing would say so.

So in the example above, `{"account_id": 2, "op": "D", "ts": 2}` deletes account 2, even though it has no `email`.

A delete with a bad or NULL key still reaches silver, where it matches no row and changes nothing. To catch bad keys in deletes, test the silver table.

## Changing a rule that quarantines

Silver is a streaming table, so a new or changed `quarantine` rule only checks rows that arrive after the change. Rows already in silver that fail it stay there, and they also appear in the quarantine table, which reads bronze from the start.

A change to a `warn` or `fail` rule moves no rows.
