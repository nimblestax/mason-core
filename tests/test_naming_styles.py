"""`mason init` offers three Naming Styles and writes each out as patterns."""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason import cli
from mason.cli import app

PLATFORM = "mason.platform.yaml"

runner = CliRunner()


def mason(project: Path, *args: str, input: str | None = None):
    return runner.invoke(app, [*args, "--project", str(project)], input=input)


def add_environment(project: Path, env: str) -> None:
    contract = project / PLATFORM
    config = yaml.safe_load(contract.read_text())
    config["environments"][env] = {"host": "https://prod.cloud.databricks.com"}
    contract.write_text(yaml.safe_dump(config, sort_keys=False))


def test_layer_catalogs_writes_its_patterns_and_resolves_a_logical_name(tmp_path: Path):
    result = mason(tmp_path, "init", "--naming-style", "layer-catalogs", "--json")
    assert result.exit_code == 0, result.output

    naming = yaml.safe_load((tmp_path / PLATFORM).read_text())["naming"]
    assert (naming["catalog"], naming["schema"]) == ("{env}_{layer}", "{domain}")
    add_environment(tmp_path, "prod")
    compiled = mason(tmp_path, "compile", "--env", "prod")
    assert compiled.exit_code == 0, compiled.output
    assert "STREAMING TABLE prod_silver.sales.orders" in compiled.stdout


STYLES = [
    ("domain-catalogs", "{env}_{domain}", "{layer}", "prod_sales.silver.orders"),
    ("layer-catalogs", "{env}_{layer}", "{domain}", "prod_silver.sales.orders"),
    ("environment-catalogs", "{env}", "{domain}_{layer}", "prod.sales_silver.orders"),
]
PATHS = {
    "domain-catalogs": "/Volumes/{env}_sales/bronze/landing/orders",
    "layer-catalogs": "/Volumes/{env}_bronze/sales/landing/orders",
    "environment-catalogs": "/Volumes/{env}/sales_bronze/landing/orders",
}


@pytest.mark.parametrize(("style", "catalog", "schema", "silver"), STYLES)
def test_each_style_writes_only_its_patterns_and_compiles(
    tmp_path: Path, style: str, catalog: str, schema: str, silver: str
):
    assert mason(tmp_path, "init", "--naming-style", style).exit_code == 0

    contract = yaml.safe_load((tmp_path / PLATFORM).read_text())
    assert set(contract) == {"kind", "version", "name", "environments", "naming", "domains"}
    assert contract["naming"] == {
        "catalog": catalog,
        "schema": schema,
        "layers": {"sources": ["bronze", "silver"], "models": ["gold"]},
    }
    assert mason(tmp_path, "validate").exit_code == 0
    add_environment(tmp_path, "prod")
    compiled = mason(tmp_path, "compile", "--env", "prod").stdout
    assert f"STREAMING TABLE {silver}" in compiled
    assert f"FROM {silver}" in compiled  # fct_orders reads `sales.silver.orders`.


@pytest.mark.parametrize("style", PATHS)
def test_the_starter_source_path_follows_the_style(tmp_path: Path, style: str):
    mason(tmp_path, "init", "--naming-style", style)

    source = yaml.safe_load((tmp_path / "domains/sales/sources/orders.yaml").read_text())
    assert source["path"] == PATHS[style]


def test_the_starter_gold_models_sit_in_their_layer_folder(tmp_path: Path):
    mason(tmp_path, "init")

    models = tmp_path / "domains/sales/models"
    assert sorted(p.name for p in models.iterdir()) == ["gold"]
    assert {p.stem for p in (models / "gold").glob("*.yaml")} == {"dim_date", "fct_orders"}
    compiled = mason(tmp_path, "compile", "--env", "dev")
    assert compiled.exit_code == 0, compiled.output
    assert "MATERIALIZED VIEW dev_sales.gold.fct_orders" in compiled.stdout
    assert "MATERIALIZED VIEW dev_sales.gold.dim_date" in compiled.stdout


@pytest.mark.parametrize(
    ("style", "catalogs", "schemas"),
    [
        (
            "domain-catalogs",
            ["dev_sales"],
            ["dev_sales.bronze", "dev_sales.silver", "dev_sales.gold"],
        ),
        (
            "layer-catalogs",
            ["dev_bronze", "dev_silver", "dev_gold"],
            ["dev_bronze.sales", "dev_silver.sales", "dev_gold.sales"],
        ),
        (
            "environment-catalogs",
            ["dev"],
            ["dev.sales_bronze", "dev.sales_silver", "dev.sales_gold"],
        ),
    ],
)
def test_init_lists_the_exact_catalogs_and_schemas_to_create(
    tmp_path: Path, style: str, catalogs: list[str], schemas: list[str]
):
    result = mason(tmp_path, "init", "--naming-style", style, "--json")

    created = json.loads(result.stdout)["result"]
    assert created["naming_style"] == style
    assert created["catalogs"] == catalogs
    assert created["schemas"] == schemas


def test_init_tells_a_person_what_to_create_and_that_any_style_fits_one_workspace(
    tmp_path: Path,
):
    result = mason(tmp_path, "init", "--naming-style", "layer-catalogs")

    assert result.exit_code == 0, result.output
    for name in ("dev_silver", "dev_silver.sales", "dev_bronze.sales"):
        assert name in result.stdout
    assert "one workspace for all Environments" in result.stdout


def naming(project: Path) -> tuple[str, str]:
    written = yaml.safe_load((project / PLATFORM).read_text())["naming"]
    return written["catalog"], written["schema"]


def test_at_a_terminal_pressing_enter_takes_domain_catalogs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)

    result = mason(tmp_path, "init", input="\n")

    assert result.exit_code == 0, result.output
    assert naming(tmp_path) == ("{env}_{domain}", "{layer}")
    for style in ("domain-catalogs", "layer-catalogs", "environment-catalogs"):
        assert style in result.output
    assert "prod_silver.sales.orders" in result.output
    assert result.output.count("one workspace for all Environments") == 2  # Prompt and output.


def test_at_a_terminal_another_style_can_be_chosen(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)

    result = mason(tmp_path, "init", input="environment-catalogs\n")

    assert result.exit_code == 0, result.output
    assert naming(tmp_path) == ("{env}", "{domain}_{layer}")


def test_with_the_flag_init_asks_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)

    result = mason(tmp_path, "init", "--naming-style", "layer-catalogs")

    assert result.exit_code == 0, result.output
    assert "Naming Style [" not in result.output
    assert naming(tmp_path) == ("{env}_{layer}", "{domain}")


def test_away_from_a_terminal_init_asks_nothing_and_takes_domain_catalogs(tmp_path: Path):
    result = mason(tmp_path, "init")

    assert result.exit_code == 0, result.output
    assert "Naming Style [" not in result.output
    assert naming(tmp_path) == ("{env}_{domain}", "{layer}")
