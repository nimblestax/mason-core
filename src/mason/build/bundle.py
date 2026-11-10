"""Writes `databricks.yaml`: the resources, plus the placeholder values for each target."""

import yaml

from mason import names, sql
from mason.kinds.platform import UNPAUSED_ENVIRONMENT
from mason.load.project import Project

REFRESH_JOB = "refresh"

# One retry survives a one-off blip. An error a retry can't fix, such as a bad row in append-only
# bronze, then fails in about a minute instead of waiting through the default five retries.
UPDATE_RETRIES = {"pipelines.numUpdateRetryAttempts": "1"}


def render(project: Project) -> str:
    platform = project.platform
    variables = list(names.settings(project, next(iter(platform.hosts))))
    pipelines = {}
    for domain in platform.domains:
        if any(item.domain == domain for item in (*project.sources, *project.seeds)):
            pipelines[f"{domain}_ingest"] = _pipeline(project, domain, "ingest")
        if any(model.domain == domain for model in project.models):
            pipelines[f"{domain}_gold"] = _pipeline(project, domain, "gold")
    upstream = _upstream(project, set(pipelines))
    tasks = [_task(pipeline, upstream.get(pipeline, [])) for pipeline in pipelines]
    return yaml.safe_dump(
        {
            "bundle": {"name": platform.name},
            # Bundle sync skips gitignored files, and `mason init` gitignores the package.
            "sync": {"include": ["src/**"]},
            "variables": {name: {"description": name} for name in variables},
            "targets": {env: _target(project, env) for env in platform.hosts},
            "resources": {
                "pipelines": pipelines,
                "jobs": {REFRESH_JOB: {"name": _name(project, "refresh"), "tasks": tasks}},
            },
        },
        sort_keys=False,
    )


def _name(project: Project, *parts: str) -> str:
    """A pipeline or Job name, with the Environment in it, so Environments can share a workspace.

    Databricks refuses a second pipeline with the same name.
    """
    return "_".join((project.platform.name, "${bundle.target}", *parts))


def _target(project: Project, env: str) -> dict:
    """One Environment's workspace and placeholder values, and its Job's schedule if it has one."""
    target: dict = {
        "workspace": {"host": project.platform.hosts[env]},
        "variables": names.settings(project, env),
    }
    schedule = project.platform.environments[env].schedule
    if schedule:
        paused = schedule.paused
        if paused is None:
            paused = env != UNPAUSED_ENVIRONMENT
        target["resources"] = {
            "jobs": {
                REFRESH_JOB: {
                    "schedule": {
                        "quartz_cron_expression": schedule.cron,
                        "timezone_id": schedule.timezone,
                        "pause_status": "PAUSED" if paused else "UNPAUSED",
                    }
                }
            }
        }
    return target


def _pipeline(project: Project, domain: str, group: str) -> dict:
    platform = project.platform
    # Every table is written by its full name, so this is only the pipeline's default. Model
    # Layers have no order, so the first by name keeps it the same however the list is ordered.
    layer = platform.source_layers[0] if group == "ingest" else min(platform.model_layers)
    keys = names.settings(project, next(iter(platform.hosts)))
    return {
        "name": _name(project, domain, group),
        "catalog": f"${{var.{names.catalog_setting(domain, layer)}}}",
        "schema": f"${{var.{names.schema_setting(domain, layer)}}}",
        "serverless": True,
        "channel": "CURRENT",
        "libraries": [{"glob": {"include": f"src/{domain}/{group}/**"}}],
        "configuration": {**{key: f"${{var.{key}}}" for key in keys}, **UPDATE_RETRIES},
    }


def _upstream(project: Project, pipelines: set[str]) -> dict[str, list[str]]:
    """The pipelines each gold pipeline reads from, so its task waits only for those.

    Ingest pipelines read only files, so they wait for nothing. Silver comes from its Domain's
    ingest pipeline, and gold of another Domain, which can only be the Shared Domain's, from its
    gold pipeline.
    """
    source_layers = {layer.lower() for layer in project.platform.source_layers}
    # Logical Names are lowercase, and pipelines are keyed by the Domain as the contract writes it.
    domains = {domain.lower(): domain for domain in project.platform.domains}
    upstream: dict[str, list[str]] = {}
    for model in project.models:
        try:
            reads = sql.reads(model.query)
        except sql.Unparseable:
            continue  # `mason validate` reports it, and `mason deploy` refuses it.
        reader = f"{model.domain}_gold"
        needed = upstream.setdefault(reader, [])
        for read in sorted(reads, key=str):
            group = "ingest" if read.layer in source_layers else "gold"
            pipeline = f"{domains.get(read.domain, read.domain)}_{group}"
            if pipeline in pipelines and pipeline != reader and pipeline not in needed:
                needed.append(pipeline)
    return upstream


def _task(pipeline: str, needs: list[str]) -> dict:
    task: dict = {
        "task_key": pipeline,
        "max_retries": 0,
        "pipeline_task": {"pipeline_id": f"${{resources.pipelines.{pipeline}.id}}"},
    }
    if needs:
        task["depends_on"] = [{"task_key": needed} for needed in needs]
    return task
