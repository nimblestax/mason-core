---
name: mason-add-model
description: Add a Gold Model to a Mason project, from its SQL and YAML files to a passing `mason validate`. Use when asked to add a gold table, a fact or a dimension.
metadata:
  mason-version: "MASON_VERSION"
  mason-digest: "MASON_DIGEST"
---

# Add a Gold Model

1. Run `mason schema model` for the fields the installed Mason accepts. Take field names and values from its output, not from memory.
2. Write `domains/<domain>/models/<layer>/<name>.sql` as one query, and `<name>.yaml` beside it with `kind: model` and the `version` the schema names.
3. Read tables by their Logical Names, such as `sales.silver.orders`, never by a real table name.
4. Run `mason validate --json`. For each diagnostic, apply its `fix`, then run it again until it reports none.
5. Run `mason compile --env dev` and read the SQL Mason generates for the model.

Stop there. Changes reach an Environment through a pull request, and a person promotes them.
