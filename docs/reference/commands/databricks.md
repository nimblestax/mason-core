---
title: brickie databricks
description: Run the Databricks CLI Brickie runs, with your arguments passed through.
generated: true
brickie_version: 0.1.0
---

```console
$ brickie databricks <arguments>
```

It runs the Databricks CLI Brickie runs, the version `brickie --version` names, with every argument passed through as you wrote it. It prints what the Databricks CLI prints and exits with its exit code, so it has no `--json`. `brickie databricks --help` prints the Databricks CLI's help.

If Brickie can't find or download its Databricks CLI, it reports a diagnostic and exits 2.
