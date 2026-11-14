"""Environments are named by the team and known to Brickie by role."""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from brickie.cli import app
from brickie.load.project import load
from brickie.scaffold import PLACEHOLDER_HOST

runner = CliRunner()

PLATFORM = "brickie.platform.yaml"
DEV_ONLY = f"environments:\n  dev:\n    host: {PLACEHOLDER_HOST}\n    role: development\n"
DV_HOST = "https://dv.example.com"
FOUR_STAGES = (
    f"environments:\n  dv:\n    host: {DV_HOST}\n    role: development\n"
    "  tst: {}\n  sit: {}\n  prd:\n    role: production\n"
)


def brickie(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def environments(project: Path, block: str) -> None:
    path = project / PLATFORM
    assert DEV_ONLY in path.read_text()
    path.write_text(path.read_text().replace(DEV_ONLY, block))


def failures(project: Path) -> list[dict]:
    result = brickie(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def test_environments_named_by_the_team_compile_to_their_own_catalogs(project: Path):
    environments(project, FOUR_STAGES)

    result = brickie(project, "compile")

    assert result.exit_code == 0, result.output
    targets = yaml.safe_load((project / "build/databricks.yaml").read_text())["targets"]
    assert list(targets) == ["dv", "tst", "sit", "prd"]
    assert targets["prd"]["workspace"]["host"] == DV_HOST
    assert targets["prd"]["variables"]["catalog_sales_silver"] == "prd_sales"
    assert targets["prd"]["variables"]["schema_sales_silver"] == "silver"


def test_a_contract_with_no_development_environment_fails_with_a_brk130(project: Path):
    environments(project, f"environments:\n  dev:\n    host: {PLACEHOLDER_HOST}\n")

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK130"
    assert diagnostic["file"] == PLATFORM
    assert "role: development" in diagnostic["fix"]


@pytest.mark.parametrize("role", ["development", "production"])
def test_two_environments_with_one_role_fail_with_a_brk131(project: Path, role: str):
    environments(
        project,
        f"environments:\n  dv:\n    host: {DV_HOST}\n    role: development\n"
        f"  dev:\n    role: {role}\n  prd:\n    role: {role}\n",
    )

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK131"
    assert f"role: {role}" in diagnostic["message"]
    assert "prd" in diagnostic["message"]


@pytest.mark.parametrize("name", ["prd-1", "1prd", "pr d"])
def test_an_environment_name_that_isnt_an_identifier_fails_with_a_brk132(project: Path, name: str):
    environments(project, f'{DEV_ONLY}  "{name}": {{}}\n')

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK132"
    assert name in diagnostic["message"]


def test_a_development_environment_with_no_host_fails_with_a_brk122_naming_it(project: Path):
    environments(
        project,
        "environments:\n  dv:\n    role: development\n  prd:\n    host: https://p.example.com\n",
    )

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK122"
    assert "environments.dv" in diagnostic["fix"]


def test_reading_commands_default_to_the_development_environment(project: Path):
    # Listed last, so neither the first Environment nor a name could be taken for it.
    environments(
        project,
        f"environments:\n  prd:\n    role: production\n  tst: {{}}\n"
        f"  dv:\n    host: {DV_HOST}\n    role: development\n",
    )

    loaded = load(project)

    assert loaded.platform.default_environment == "dv"
    assert loaded.platform.hosts == dict.fromkeys(("prd", "tst", "dv"), DV_HOST)


def test_a_version_1_contract_upgrades_with_roles_on_dev_and_prod(project: Path):
    (project / PLATFORM).write_text(
        "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
        "    host: https://dev.example.com\n  test: {}\n  prod:\n"
        "    host: https://prod.example.com\n"
        'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
        "  layers:\n    models: [gold]\ndomains:\n  - sales\n"
    )

    loaded = load(project)

    roles = {env: settings.role for env, settings in loaded.platform.environments.items()}
    assert roles == {"dev": "development", "test": None, "prod": "production"}
    assert loaded.platform.default_environment == "dev"


SCHEDULE = "\n    schedule:\n      cron: 0 0 6 * * ?\n"


def test_a_schedule_runs_in_the_production_environment_and_is_paused_elsewhere(project: Path):
    environments(
        project,
        f"environments:\n  dv:\n    host: {DV_HOST}\n    role: development\n"
        f"  prod:{SCHEDULE}  prd:\n    role: production{SCHEDULE}",
    )

    assert brickie(project, "compile").exit_code == 0
    targets = yaml.safe_load((project / "build/databricks.yaml").read_text())["targets"]
    pause_status = {
        env: targets[env]["resources"]["jobs"]["refresh"]["schedule"]["pause_status"]
        for env in ("prod", "prd")
    }
    assert pause_status == {"prod": "PAUSED", "prd": "UNPAUSED"}
