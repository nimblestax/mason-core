"""`brickie validate --platform`: the platform objects a project needs exist in its workspace."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brickie import cli
from brickie.cli import app
from brickie.deploy import deploy, pinned_cli
from brickie.load.project import load

runner = CliRunner()

HOST = "https://kettle.cloud.databricks.com"


class FakeUnityCatalog:
    """A workspace's catalogs and schemas, as the Databricks boundary reports them."""

    def __init__(self, schemas: dict[str, set[str]]):
        self.schemas_by_catalog = schemas
        self.calls: list[tuple] = []

    def catalogs(self, host: str) -> set[str]:
        self.calls.append(("catalogs", host))
        return set(self.schemas_by_catalog)

    def schemas(self, host: str, catalog: str) -> set[str]:
        self.calls.append(("schemas", host, catalog))
        return self.schemas_by_catalog[catalog]


def brickie(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path), "--host", HOST]).exit_code == 0
    return tmp_path


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch) -> FakeUnityCatalog:
    """Everything `brickie init` lists for dev, until a test takes something away."""
    fake = FakeUnityCatalog({"dev_sales": {"bronze", "silver", "gold"}})
    monkeypatch.setattr(cli, "DatabricksCli", lambda: fake)
    return fake


def test_a_missing_catalog_fails_with_a_rule_naming_it(project: Path, workspace: FakeUnityCatalog):
    del workspace.schemas_by_catalog["dev_sales"]

    result = brickie(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "BRK301"
    assert "dev_sales" in diagnostic["message"]


def test_plain_validate_makes_no_workspace_call(project: Path, workspace: FakeUnityCatalog):
    del workspace.schemas_by_catalog["dev_sales"]

    result = brickie(project, "validate", "--json")

    assert result.exit_code == 0, result.output
    assert workspace.calls == []


def test_a_missing_schema_fails_with_a_rule_naming_it(project: Path, workspace: FakeUnityCatalog):
    workspace.schemas_by_catalog["dev_sales"] = {"bronze", "gold"}

    result = brickie(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "BRK302"
    assert "dev_sales.silver" in diagnostic["message"]


PROD_HOST = "https://kettle-prod.cloud.databricks.com"


def add_prod(project: Path, host: str | None) -> None:
    contract = project / "brickie.platform.yaml"
    settings = "\n    role: production" + (f"\n    host: {host}" if host else "")
    contract.write_text(
        contract.read_text().replace("naming:\n", f"  prod:{settings}\nnaming:\n", 1)
    )


def test_env_checks_that_environment_in_its_own_workspace(
    project: Path, workspace: FakeUnityCatalog
):
    add_prod(project, PROD_HOST)
    workspace.schemas_by_catalog = {"prod_sales": {"bronze", "silver", "gold"}}

    result = brickie(project, "validate", "--platform", "--env", "prod", "--json")

    assert result.exit_code == 0, result.output
    assert workspace.calls == [
        ("catalogs", PROD_HOST),
        ("schemas", PROD_HOST, "prod_sales"),
    ]


@pytest.mark.parametrize("host", [None, PROD_HOST])
def test_prod_in_a_shared_or_its_own_workspace_validates_with_no_warning(
    project: Path, host: str | None
):
    # Every Naming Style puts the Environment in the catalog, so a shared workspace shares no
    # table, and its identities and grants are nothing Brickie checks.
    add_prod(project, host)

    result = brickie(project, "validate", "--json")

    assert json.loads(result.stdout)["diagnostics"] == []


class ShippingWorkspace:
    def __init__(self) -> None:
        self.deployed: list[str] = []

    def deploy_bundle(self, package: Path, target: str) -> None:
        self.deployed.append(target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        pass

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        return []


def test_the_warning_never_stops_a_deploy(project: Path):
    add_prod(project, None)
    workspace = ShippingWorkspace()

    deploy.deploy(load(project), "prod", workspace)

    assert workspace.deployed == ["prod"]


def test_the_generated_ci_checks_the_platform_as_dev_before_anything_else(project: Path):
    workflows = project / ".github/workflows"
    pull_request = (workflows / "brickie-pull-request.yaml").read_text()
    merge = (workflows / "brickie-merge.yaml").read_text()

    assert "brickie validate --platform --env dev" in pull_request
    assert "brickie validate --platform --env dev" in merge
    assert merge.index("brickie validate --platform") < merge.index("brickie deploy")
    # The check signs in, so the pull request job needs dev's identity.
    assert "id-token: write" in pull_request
    assert "environment: dev" in pull_request
    assert "DATABRICKS_AUTH_TYPE: github-oidc" in pull_request


def fake_cli(folder: Path, catalogs: list[str], schemas: list[str]) -> Path:
    """A Databricks CLI that answers the two listings and records each call with its host."""
    script = folder / "fake-databricks"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "$DATABRICKS_HOST $@" >> {folder}/calls\n'
        'case "$1 $2" in\n'
        f'  "--version ") echo "Databricks CLI v{pinned_cli.MINIMUM}" ;;\n'
        f"  \"catalogs list\") echo '{json.dumps([{'name': name} for name in catalogs])}' ;;\n"
        f"  \"schemas list\") echo '{json.dumps([{'name': name} for name in schemas])}' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    script.chmod(0o755)
    return script


def test_the_databricks_cli_lists_catalogs_and_schemas_in_the_environments_workspace(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cli_folder = tmp_path / "cli"
    cli_folder.mkdir()
    script = fake_cli(cli_folder, ["DEV_SALES", "main"], ["bronze", "gold"])
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(script))
    monkeypatch.setenv("DATABRICKS_HOST", "https://somewhere-else.cloud.databricks.com")

    result = brickie(project, "validate", "--platform", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "BRK302"
    assert "dev_sales.silver" in diagnostic["message"]
    calls = (cli_folder / "calls").read_text().splitlines()
    assert f"{HOST} catalogs list --output json" in calls
    assert f"{HOST} schemas list dev_sales --output json" in calls


def test_env_without_platform_is_a_usage_error(project: Path, workspace: FakeUnityCatalog):
    result = brickie(project, "validate", "--env", "dev", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "BRK901"
    assert "--platform" in diagnostic["fix"]
