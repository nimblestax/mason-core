---
title: mason databricks
description: Run the Databricks CLI Mason runs, with your arguments passed through.
generated: true
mason_version: 0.3.0
---

```console
$ mason databricks <arguments>
```

It runs the Databricks CLI Mason runs, the version `mason --version` names, with every argument passed through as you wrote it. It prints what the Databricks CLI prints and exits with its exit code, so it has no `--json`. `mason databricks --help` prints the Databricks CLI's help.

If Mason can't find or download its Databricks CLI, it reports a diagnostic and exits 2.
