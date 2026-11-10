---
title: Mason skills
description: The agent skills mason init writes into your repo, why there are two copies, and how they stay in step with Mason.
---

A Mason skill guides a coding agent through one task with Mason's commands, such as adding a source. `mason init` writes them into your project, and you commit them like any other file.

```console
$ mason init kettle
...
Wrote Mason Skills for coding agents:
  .agents/skills/mason-add-model
  .claude/skills/mason-add-model
  .agents/skills/mason-add-source
  .claude/skills/mason-add-source
```

Each skill is one `SKILL.md` that names the commands to run. It doesn't list a kind's fields. It tells the agent to run `mason schema <kind>`, so the fields come from the Mason you have installed. No skill deploys: an agent writes the change, and a person promotes it.

## Where they go

Skills follow the [Agent Skills](https://agentskills.io) standard and use only its fields, so every agent that reads the standard gets the same steps.

`.agents/skills/` holds the main copy, in the folder many coding agents share. Claude Code reads only `.claude/skills/`, so it gets an identical copy. They are copies, not symlinks, because symlinks don't check out reliably on Windows.

Mason only ever adds `mason-*` folders. Your own skills, settings and other files in `.agents/` and `.claude/` stay as they are, and a `mason-*` folder that already exists is left alone. If Git ignores either folder, `mason init` warns with [`MSN914`](../reference/rules/msn914.md), because skills that aren't committed stay on one machine.

To write no skills, run `mason init --skills none`. `mason skills update` writes them later if you change your mind.

## Keeping them in step

Each skill records the Mason version that wrote it, in its front matter:

```yaml
metadata:
  mason-version: "0.3.0"
  mason-digest: "..."
```

After you upgrade Mason, `mason validate` warns with [`MSN129`](../reference/rules/msn129.md) for each skill an older version wrote, because its steps can name commands that have changed. A warning doesn't fail validation.

`mason skills update` rewrites both copies of each skill to the installed version:

```console
$ mason skills update
Updated these Mason Skills. Commit them:
  .agents/skills/mason-add-source
  .claude/skills/mason-add-source
```

`mason-digest` records the text Mason wrote, so `mason skills update` can tell your edit from an older Mason's text. If you edited a skill, it writes nothing, reports [`MSN915`](../reference/rules/msn915.md) and shows the difference. Move your steps into a skill of your own, outside the `mason-*` folders, or run `mason skills update --force` to replace them.

## Next steps

- [`mason skills update`](../reference/commands/skills-update.md) lists its options and its JSON result.
- [`mason init`](../reference/commands/init.md) lists `--skills` with its other options.
