---
title: Seed
description: Small reference data kept in Git and fully replaced on each deploy.
generated: true
mason_version: 0.3.0
---

A file with `kind: seed`, at version 1. `mason schema seed` prints the same fields from the Mason you installed.

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `kind` | `seed` | yes |  | The Kind of this file. |
| `version` | `1` | yes |  | The schema version of this Kind. |
| `file` | string | yes |  | The data file, in the same folder as this file. |
| `columns` | map of name to string | yes |  | Each column's name and SQL type. An empty value in the file is NULL. |
| `export` | boolean | no | `false` | Whether other Domains' Gold Models and the Shared Domain may read this Seed. A Seed is private to its Domain otherwise. |
