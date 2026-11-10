---
title: Schedule refreshes
description: Refresh an Environment's tables on a schedule, set in mason.platform.yaml, and paused outside prod unless you say otherwise.
---

Each Environment has one Job that refreshes every pipeline. `mason deploy` runs it once after each deploy. A schedule also runs it on its own.

## Add a schedule

Add `schedule` under the Environment in `mason.platform.yaml`:

```yaml
environments:
  dev:
    host: https://kettle.cloud.databricks.com
  test: {}
  prod:
    schedule:
      cron: 0 0 6 * * ?
      timezone: Australia/Sydney
```

`cron` is a [Quartz cron expression](https://www.quartz-scheduler.org/documentation/quartz-2.3.0/tutorials/crontrigger.html): `0 0 6 * * ?` is 6am every day. `timezone` is optional. Left out, it's `UTC`.

Compile to see the schedule Databricks receives:

```shell
mason compile
```

```text
Wrote build
```

The prod target in `build/databricks.yaml` now sets the Job's schedule:

```yaml
  prod:
    resources:
      jobs:
        refresh:
          schedule:
            quartz_cron_expression: 0 0 6 * * ?
            timezone_id: Australia/Sydney
            pause_status: UNPAUSED
```

The schedule takes effect at the next `mason deploy --env prod`.

## Schedule an Environment other than prod

A schedule in any Environment other than prod is paused, so lower Environments don't spend money unasked. To run it, set `paused: false`:

```yaml
  test:
    schedule:
      cron: 0 0 7 * * ?
      paused: false
```

To pause prod's schedule, set `paused: true` and deploy.

## Remove a schedule

Delete `schedule` and deploy. The Job then runs only when `mason deploy` runs it.

## Next steps

- Every field of `schedule` is in the [Platform Contract reference](../reference/kinds/platform.md).
- If a refresh fails, see [Recover from a failed refresh](recover-from-a-failed-refresh.md).
