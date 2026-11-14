---
title: Brickie skills
description: The agent skills brickie init writes into your repo, why there are two copies, and how they stay in step with Brickie.
---

A Brickie skill guides a coding agent through one task with Brickie's commands, such as adding a source. `brickie init` writes them into your project, and you commit them like any other file.

```console
$ brickie init kettle
...
Wrote Brickie Skills for coding agents:
  .agents/skills/brickie-add-model
  .claude/skills/brickie-add-model
  .agents/skills/brickie-add-source
  .claude/skills/brickie-add-source
```

Each skill is one `SKILL.md` that names the commands to run. It doesn't list a kind's fields. It tells the agent to run `brickie schema <kind>`, so the fields come from the Brickie you have installed. No skill deploys: an agent writes the change, and a person promotes it.

## Where they go

Skills follow the [Agent Skills](https://agentskills.io) standard and use only its fields, so every agent that reads the standard gets the same steps.

`.agents/skills/` holds the main copy, in the folder many coding agents share. Claude Code reads only `.claude/skills/`, so it gets an identical copy. They are copies, not symlinks, because symlinks don't check out reliably on Windows.

Brickie only ever adds `brickie-*` folders. Your own skills, settings and other files in `.agents/` and `.claude/` stay as they are, and a `brickie-*` folder that already exists is left alone. If Git ignores either folder, `brickie init` warns with [`BRK914`](../reference/rules/brk914.md), because skills that aren't committed stay on one machine.

To write no skills, run `brickie init --skills none`. `brickie skills update` writes them later if you change your mind.

## Keeping them in step

Each skill records the Brickie version that wrote it, in its front matter:

```yaml
metadata:
  brickie-version: "0.1.0"
  brickie-digest: "..."
```

After you upgrade Brickie, `brickie validate` warns with [`BRK129`](../reference/rules/brk129.md) for each skill an older version wrote, because its steps can name commands that have changed. A warning doesn't fail validation.

`brickie skills update` rewrites both copies of each skill to the installed version:

```console
$ brickie skills update
Updated these Brickie Skills. Commit them:
  .agents/skills/brickie-add-source
  .claude/skills/brickie-add-source
```

`brickie-digest` records the text Brickie wrote, so `brickie skills update` can tell your edit from an older Brickie's text. If you edited a skill, it writes nothing, reports [`BRK915`](../reference/rules/brk915.md) and shows the difference. Move your steps into a skill of your own, outside the `brickie-*` folders, or run `brickie skills update --force` to replace them.

## Next steps

- [`brickie skills update`](../reference/commands/skills.md#update) lists its options and its JSON result.
- [`brickie init`](../reference/commands/init.md) lists `--skills` with its other options.
