"""The Platform Contract, described once by a Pydantic model."""

import json
import shutil
from pathlib import Path
from typing import Literal

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel
from typer.testing import CliRunner

from brickie.cli import app
from brickie.kinds import platform
from brickie.load import config
from brickie.load.project import load
from brickie.scaffold import PLACEHOLDER_HOST

runner = CliRunner()

PLATFORM = "brickie.platform.yaml"


def brickie(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def edit(project: Path, old: str, new: str) -> None:
    path = project / PLATFORM
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))


def failures(project: Path) -> list[dict]:
    result = brickie(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


@pytest.mark.parametrize(
    ("old", "new", "field"),
    [
        ("version: 2\n", 'version: "2"\n', "version"),
        ("version: 2\n", "version: true\n", "version"),
        ("domains:\n", "colour: blue\ndomains:\n", "colour"),
        ("    models: [gold]\n", "    models: gold\n", "naming.layers.models"),
        ("  style: domain-catalogs\n", "  style: 7\n", "naming.style"),
    ],
)
def test_a_bad_platform_contract_names_the_field_in_a_brk106(
    project: Path, old: str, new: str, field: str
):
    edit(project, old, new)

    diagnostics = failures(project)

    assert {d["rule"] for d in diagnostics} == {"BRK106"}
    assert any(d["message"].startswith(f"{field}: ") for d in diagnostics), diagnostics
    assert all(d["file"] == PLATFORM for d in diagnostics)


def platform_schema() -> dict:
    result = runner.invoke(app, ["schema", "platform", "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)["result"]["json_schema"]


def test_the_served_schema_passes_a_valid_contract_and_fails_invalid_ones(project: Path):
    validator = Draft202012Validator(platform_schema())
    contract = yaml.safe_load((project / PLATFORM).read_text())

    assert list(validator.iter_errors(contract)) == []
    for bad in ({"version": "2"}, {"version": True}, {"colour": "blue"}, {"name": 7}):
        assert list(validator.iter_errors({**contract, **bad})), bad


def test_the_served_schema_titles_and_describes_every_field():
    json_schema = platform_schema()

    assert json_schema["title"] == "Brickie Platform Contract"
    objects = [json_schema, *json_schema["$defs"].values()]
    for described in objects:
        assert described["title"] and described["description"]
        for name, field in described["properties"].items():
            assert field["description"], name


def test_the_text_schema_lists_every_field_with_its_description():
    result = runner.invoke(app, ["schema", "platform"])

    assert result.exit_code == 0, result.output
    assert "naming (required): The Naming Style" in result.stdout
    assert "domains (required)" in result.stdout


def test_a_valid_contract_loads_with_its_layers_and_hosts(project: Path):
    loaded = load(project)

    assert loaded.platform.source_layers == ("bronze", "silver")
    assert loaded.platform.model_layers == ("gold",)
    assert loaded.platform.hosts == {"dev": PLACEHOLDER_HOST}


def test_a_repeated_domain_names_the_field(project: Path):
    edit(project, "  - sales\n", "  - sales\n  - sales\n")

    [diagnostic] = failures(project)

    assert diagnostic["message"].startswith("domains: ")
    assert "sales" in diagnostic["message"]


class PlatformV3(BaseModel):
    """A stand-in third version that renames `name` to `project`."""

    model_config = platform.STRICT

    kind: Literal["platform"]
    version: Literal[3]
    project: str


def upgrade_to_v3(old: platform.PlatformV2) -> PlatformV3:
    return PlatformV3(kind="platform", version=3, project=old.name)


VERSION_1 = (
    "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
    "    host: https://dev.example.com\n"
    'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
    "  layers:\n    sources: [bronze, silver]\n    models: [gold]\ndomains:\n  - sales\n"
)


@pytest.mark.parametrize("written", [1, 2])
def test_a_contract_is_upgraded_through_every_step_to_the_latest_version(
    project: Path, monkeypatch, written: int
):
    monkeypatch.setattr(
        platform, "VERSIONS", {1: platform.PlatformV1, 2: platform.PlatformV2, 3: PlatformV3}
    )
    monkeypatch.setattr(platform, "UPGRADES", {1: platform.upgrade_to_v2, 2: upgrade_to_v3})
    if written == 1:
        (project / PLATFORM).write_text(VERSION_1)
    name = yaml.safe_load((project / PLATFORM).read_text())["name"]

    upgraded = config.load(project, project / PLATFORM, platform.KIND, PlatformV3)

    assert upgraded == PlatformV3(kind="platform", version=3, project=name)


@pytest.mark.parametrize(
    ("new", "field"),
    [
        ('  catalog: "{env}_{team}"', "naming.catalog"),
        ('  catalog: "{env}_{0}"', "naming.catalog"),
        ('  catalog: "{env}_{domain"', "naming.catalog"),
        ('  schema: "{layer}_}"', "naming.schema"),
        ('  schema: "{layer!r}"', "naming.schema"),
    ],
)
def test_a_version_1_pattern_with_anything_but_known_placeholders_fails_with_a_brk106(
    project: Path, new: str, field: str
):
    old = '  catalog: "{env}_{domain}"' if "catalog" in new else '  schema: "{layer}"'
    (project / PLATFORM).write_text(VERSION_1.replace(old, new))

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK106"
    assert diagnostic["message"].startswith(f"{field}: ")
    assert "{env}, {domain} and {layer}" in diagnostic["message"]


def test_a_project_with_no_domains_compiles_to_a_package_with_no_pipelines(project: Path):
    edit(project, "domains:\n  - sales\n", "domains: []\n")
    shutil.rmtree(project / "domains")

    result = brickie(project, "compile")

    assert result.exit_code == 0, result.output
    bundle = yaml.safe_load((project / "build/databricks.yaml").read_text())
    assert bundle["resources"]["pipelines"] == {}


DEV_ONLY = "environments:\n  dev:\n    host: {host}\n    role: development\n"


def environments(project: Path, block: str) -> None:
    edit(project, DEV_ONLY.format(host=PLACEHOLDER_HOST), block)


def test_test_and_prod_use_devs_host_unless_they_set_their_own(project: Path):
    environments(
        project,
        "environments:\n  dev:\n    host: https://dev.example.com\n    role: development\n"
        "  test: {}\n"
        "  prod:\n    host: https://prod.example.com\n",
    )

    loaded = load(project)

    assert loaded.platform.hosts == {
        "dev": "https://dev.example.com",
        "test": "https://dev.example.com",
        "prod": "https://prod.example.com",
    }


def test_a_contract_with_no_host_on_dev_fails_with_a_brk122(project: Path):
    environments(
        project,
        "environments:\n  dev:\n    role: development\n"
        "  prod:\n    host: https://prod.example.com\n",
    )

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK122"
    assert diagnostic["file"] == PLATFORM
    assert "dev" in diagnostic["fix"]


def test_two_default_environments_fail_with_a_brk123(project: Path):
    environments(
        project,
        f"environments:\n  dev:\n    host: {PLACEHOLDER_HOST}\n    role: development\n"
        "    default: true\n"
        "  test:\n    default: true\n  prod: {}\n",
    )

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "BRK123"
    assert "dev" in diagnostic["message"] and "test" in diagnostic["message"]


@pytest.mark.parametrize(
    ("test_settings", "default"), [("{}", "dev"), ("\n    default: true", "test")]
)
def test_the_default_environment_is_the_one_marked_default_or_else_dev(
    project: Path, test_settings: str, default: str
):
    environments(project, DEV_ONLY.format(host=PLACEHOLDER_HOST) + f"  test: {test_settings}\n")

    assert load(project).platform.default_environment == default


@pytest.mark.parametrize("marked", ["", "    default: true\n"])
def test_deploy_without_env_exits_2_with_a_fix_whatever_the_default(project: Path, marked: str):
    environments(project, DEV_ONLY.format(host=PLACEHOLDER_HOST) + marked)

    result = brickie(project, "deploy", "--json")

    assert result.exit_code == 2, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "BRK901"
    assert "--env dev" in diagnostic["fix"]


def test_a_contract_with_a_host_on_every_environment_validates_unchanged(project: Path):
    hosts = {env: f"https://{env}.example.com" for env in ("dev", "test", "prod")}
    roles = {"dev": "development", "test": None, "prod": "production"}
    environments(
        project,
        "environments:\n"
        + "".join(
            f"  {env}:\n    host: {h}\n" + (f"    role: {roles[env]}\n" if roles[env] else "")
            for env, h in hosts.items()
        ),
    )

    result = brickie(project, "validate")

    assert result.exit_code == 0, result.output
    assert load(project).platform.hosts == hosts
