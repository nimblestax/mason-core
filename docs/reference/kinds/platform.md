---
title: Platform Contract
description: The shared facts about a project's platform.
generated: true
mason_version: 0.3.0
---

A file with `kind: platform`, at version 1. `mason schema platform` prints the same fields from the Mason you installed.

## Fields

| Field | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `kind` | `platform` | yes |  | The Kind of this file. |
| `version` | `1` | yes |  | The schema version of this Kind. |
| `name` | string | yes |  | The project's name. |
| `environments` | map of name to object | yes |  | Settings per Environment. |
| `environments.<name>.host` | string | no | `null` | Workspace URL. Required on dev; test and prod use dev's unless they set their own. |
| `environments.<name>.default` | boolean | no | `false` | Whether commands that read use this Environment when `--env` is left out. At most one Environment sets it; with none, dev is the default. `mason deploy` always needs `--env`. |
| `naming` | object | yes |  | The catalog and schema patterns, and the Layers. |
| `naming.catalog` | string | yes |  | The catalog pattern, built from `{env}`, `{domain}` and `{layer}`. |
| `naming.schema` | string | yes |  | The schema pattern, built from `{env}`, `{domain}` and `{layer}`. |
| `naming.layers` | object | yes |  | The source and model Layers. |
| `naming.layers.sources` | list of string | yes |  | Exactly two source Layers, bronze then silver. |
| `naming.layers.models` | list of string | yes |  | One or more model Layers, read left to right. |
| `domains` | list of string | yes |  | The Domains, one folder each under `domains/`. |
