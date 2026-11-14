---
name: brickie-add-source
description: Add a Source to a Brickie project, from its YAML file to a passing `brickie validate`. Use when asked to add, declare or ingest a new source of landed files.
metadata:
  brickie-version: "BRICKIE_VERSION"
  brickie-digest: "BRICKIE_DIGEST"
---

# Add a Source

1. Run `brickie schema source` for the fields the installed Brickie accepts. Take field names and values from its output, not from memory.
2. Write `domains/<domain>/sources/<name>.yaml` with `kind: source` and the `version` the schema names. `<domain>` must be listed under `domains` in `brickie.platform.yaml`.
3. Run `brickie validate --json`. For each diagnostic, apply its `fix`, then run it again until it reports none.
4. Run `brickie compile --env dev` and read the SQL Brickie generates for the Source.

Stop there. Changes reach an Environment through a pull request, and a person promotes them.
