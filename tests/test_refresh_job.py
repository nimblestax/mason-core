"""One Job per Environment runs every pipeline. A task waits only for the pipelines whose tables it
reads, so a failure skips only what depends on it."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason.cli import app
from mason.deploy import pinned_cli
from mason.load.project import load

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


def init(project: Path, *args: str) -> Path:
    """The project `mason init` writes, with a `finance` Domain beside `sales`."""
    assert runner.invoke(app, ["init", str(project), *args]).exit_code == 0
    platform = project / "mason.platform.yaml"
    platform.write_text(platform.read_text().replace("  - sales\n", "  - sales\n  - finance\n"))
    return project


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return init(tmp_path)


def add_domain(project: Path, domain: str) -> None:
    platform = project / "mason.platform.yaml"
    platform.write_text(platform.read_text().replace("  - sales\n", f"  - sales\n  - {domain}\n"))


def write_source(project: Path, domain: str, name: str, silver: str = "") -> None:
    folder = project / "domains" / domain / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(
        f"kind: source\nversion: 1\npath: /Volumes/{{env}}_{domain}/bronze/landing/{name}\n"
        f"format: json\n{silver}"
    )


def write_model(project: Path, domain: str, name: str, query: str) -> None:
    folder = project / "domains" / domain / "models/gold"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(f"kind: model\nversion: 1\nsql: {name}.sql\n")
    (folder / f"{name}.sql").write_text(query)


def set_environments(project: Path, block: str) -> None:
    platform = project / "mason.platform.yaml"
    text = platform.read_text()
    start, end = text.index("environments:\n"), text.index("naming:\n")
    platform.write_text(text[:start] + block + text[end:])


def compiled(project: Path) -> dict:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    return yaml.safe_load((project / "build/databricks.yaml").read_text())


def waits_for(bundle: dict) -> dict[str, set[str]]:
    [job] = bundle["resources"]["jobs"].values()
    return {
        task["task_key"]: {needed["task_key"] for needed in task.get("depends_on", [])}
        for task in job["tasks"]
    }


def test_a_domain_waits_for_another_only_where_it_reads_that_domains_exported_silver(
    project: Path,
):
    write_source(project, "finance", "invoices", "silver:\n  export: true\n")
    write_source(project, "finance", "ledger")
    write_model(project, "finance", "fct_ledger", "SELECT * FROM finance.silver.ledger")
    write_model(
        project,
        "sales",
        "fct_revenue",
        "SELECT o.order_id FROM sales.silver.orders o JOIN finance.silver.invoices i"
        " ON o.order_id = i.order_id",
    )

    assert waits_for(compiled(project)) == {
        "sales_ingest": set(),
        "sales_gold": {"sales_ingest", "finance_ingest"},
        "finance_ingest": set(),
        "finance_gold": {"finance_ingest"},
    }


def test_unrelated_domains_share_no_task_dependency(project: Path):
    write_source(project, "finance", "ledger")
    write_model(project, "finance", "fct_ledger", "SELECT * FROM finance.silver.ledger")

    assert waits_for(compiled(project)) == {
        "sales_ingest": set(),
        "sales_gold": {"sales_ingest"},
        "finance_ingest": set(),
        "finance_gold": {"finance_ingest"},
    }


def test_a_domain_that_reads_the_shared_domains_gold_waits_for_it(project: Path):
    add_domain(project, "shared")
    write_source(project, "shared", "calendar")
    write_model(project, "shared", "dim_calendar", "SELECT * FROM shared.silver.calendar")
    write_model(project, "finance", "fct_days", "SELECT * FROM shared.gold.dim_calendar")

    assert waits_for(compiled(project)) == {
        "sales_ingest": set(),
        "sales_gold": {"sales_ingest"},
        "shared_ingest": set(),
        "shared_gold": {"shared_ingest"},
        "finance_gold": {"shared_gold"},
    }


def validated(project: Path, workspace: str, target: str) -> dict:
    """The resources `databricks bundle validate` reads from the package for one target."""
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(project),
        "DATABRICKS_HOST": workspace,
        "DATABRICKS_TOKEN": "not-a-real-token",
    }
    result = subprocess.run(
        [pinned_cli.databricks(), "bundle", "validate", "--target", target, "--output", "json"],
        cwd=project / "build",
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["resources"]


def test_environments_in_one_workspace_each_get_their_own_job_and_pipelines(
    tmp_path: Path, stub_workspace: str
):
    project = init(tmp_path, "--host", stub_workspace)
    set_environments(project, f"environments:\n  dev:\n    host: {stub_workspace}\n  test: {{}}\n")
    compiled(project)

    name = load(project).platform.name
    for env in ("dev", "test"):
        resources = validated(project, stub_workspace, env)
        [job] = resources["jobs"].values()
        pipelines = {pipeline["name"] for pipeline in resources["pipelines"].values()}
        assert job["name"] == f"{name}_{env}_refresh"
        assert pipelines == {f"{name}_{env}_sales_ingest", f"{name}_{env}_sales_gold"}


DAILY = "    schedule:\n      cron: 0 0 6 * * ?\n      timezone: Australia/Sydney\n"


def test_each_environment_runs_on_its_own_schedule_paused_outside_prod_by_default(
    tmp_path: Path, stub_workspace: str
):
    project = init(tmp_path, "--host", stub_workspace)
    set_environments(
        project,
        f"environments:\n  dev:\n    host: {stub_workspace}\n{DAILY}  test:\n{DAILY}"
        f"  prod:\n{DAILY}",
    )
    compiled(project)

    for env, paused in (("dev", "PAUSED"), ("test", "PAUSED"), ("prod", "UNPAUSED")):
        [job] = validated(project, stub_workspace, env)["jobs"].values()
        assert job["schedule"] == {
            "quartz_cron_expression": "0 0 6 * * ?",
            "timezone_id": "Australia/Sydney",
            "pause_status": paused,
        }


def test_an_environment_can_say_whether_its_schedule_is_paused(project: Path):
    set_environments(
        project,
        "environments:\n  dev:\n    host: https://dev.example.com\n"
        f"{DAILY}      paused: false\n  prod:\n{DAILY}      paused: true\n",
    )

    targets = compiled(project)["targets"]

    assert targets["dev"]["resources"]["jobs"]["refresh"]["schedule"]["pause_status"] == "UNPAUSED"
    assert targets["prod"]["resources"]["jobs"]["refresh"]["schedule"]["pause_status"] == "PAUSED"


def test_an_environment_with_no_schedule_runs_only_when_deployed(project: Path):
    bundle = compiled(project)

    assert "resources" not in bundle["targets"]["dev"]
    assert "schedule" not in bundle["resources"]["jobs"]["refresh"]
