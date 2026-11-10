---
name: mason-add-source
description: Add a Source to a Mason project, from its YAML file to a passing `mason validate`. Use when asked to add, declare or ingest a new source of landed files.
metadata:
  mason-version: "MASON_VERSION"
  mason-digest: "MASON_DIGEST"
---

# Add a Source

1. Run `mason schema source` for the fields the installed Mason accepts. Take field names and values from its output, not from memory.
2. Write `domains/<domain>/sources/<name>.yaml` with `kind: source` and the `version` the schema names. `<domain>` must be listed under `domains` in `mason.platform.yaml`.
3. Run `mason validate --json`. For each diagnostic, apply its `fix`, then run it again until it reports none.
4. Run `mason compile --env dev` and read the SQL Mason generates for the Source.

Stop there. Changes reach an Environment through a pull request, and a person promotes them.
