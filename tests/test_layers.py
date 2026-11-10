"""Source Layers are always bronze and silver. A project names its model Layers, in no order."""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason.cli import app

PLATFORM = "mason.platform.yaml"

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def set_model_layers(project: Path, *layers: str) -> None:
    platform = project / PLATFORM
    listed = ", ".join(layers)
    platform.write_text(platform.read_text().replace("models: [gold]", f"models: [{listed}]"))


def write_model(project: Path, path: str, query: str) -> None:
    config = project / "domains" / path
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(f"kind: model\nversion: 1\nsql: {config.stem}.sql\n")
    config.with_suffix(".sql").write_text(query)


def diagnostics(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def passes(project: Path) -> None:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 0, result.output


def test_a_model_in_a_second_layer_resolves_and_reads_gold(project: Path):
    set_model_layers(project, "gold", "marts")
    write_model(project, "sales/models/marts/x.yaml", "SELECT * FROM sales.gold.dim_date")
    write_model(project, "sales/models/gold/y.yaml", "SELECT * FROM sales.marts.x")

    passes(project)
    compiled = mason(project, "compile", "--env", "dev")
    assert compiled.exit_code == 0, compiled.output
    assert "MATERIALIZED VIEW dev_sales.marts.x" in compiled.stdout


def test_a_loop_across_model_layers_fails_with_msn208(project: Path):
    set_model_layers(project, "gold", "marts")
    write_model(project, "sales/models/gold/a.yaml", "SELECT * FROM sales.marts.b")
    write_model(project, "sales/models/marts/b.yaml", "SELECT * FROM sales.gold.a")

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN208"
    assert "sales.gold.a → sales.marts.b → sales.gold.a" in failure["message"]


def write_version_1_contract(project: Path, sources: str) -> None:
    """`mason.platform.yaml` as Mason 0.3.0 wrote it, with its own `naming.layers.sources`."""
    (project / PLATFORM).write_text(
        "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
        "    host: https://your-workspace.cloud.databricks.com\n"
        'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
        f"  layers:\n    sources: {sources}\n    models: [gold]\ndomains:\n  - sales\n"
    )


@pytest.mark.parametrize(
    "layers", ["[bronze, curated]", "[bronze, silver, curated]", "[silver, bronze]"]
)
def test_source_layers_other_than_bronze_and_silver_fail_and_point_to_a_model_layer(
    project: Path, layers: str
):
    write_version_1_contract(project, layers)

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN125"
    assert failure["file"] == PLATFORM
    assert "bronze and silver" in failure["message"]
    assert "naming.layers.models" in failure["fix"]


def test_source_layers_written_as_bronze_and_silver_still_pass(project: Path):
    write_version_1_contract(project, "[bronze, silver]")

    passes(project)


def test_init_no_longer_writes_source_layers(project: Path):
    assert "sources:" not in (project / PLATFORM).read_text()
    passes(project)


@pytest.mark.parametrize("layer", ["silver", "Bronze"])
def test_a_model_layer_named_like_a_source_layer_fails(project: Path, layer: str):
    set_model_layers(project, "gold", layer)

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN126"
    assert failure["name"] == "model-layer-named-like-a-source-layer"
    assert failure["file"] == PLATFORM
    assert layer in failure["message"]


@pytest.mark.parametrize("path", ["sales/models/x.yaml", "sales/models/serving/x.yaml"])
def test_a_model_outside_a_model_layer_folder_fails_listing_the_layers(project: Path, path: str):
    set_model_layers(project, "gold", "marts")
    write_model(project, path, "SELECT * FROM sales.gold.dim_date")

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN127"
    assert failure["name"] == "model-outside-a-layer"
    assert failure["file"] == f"domains/{path}"
    assert "gold" in failure["fix"] and "marts" in failure["fix"]


def test_deeper_folders_are_read_and_change_nothing_about_the_table(project: Path):
    sales = project / "domains/sales"
    (sales / "sources/erp/eu").mkdir(parents=True)
    (sales / "sources/orders.yaml").rename(sales / "sources/erp/eu/orders.yaml")
    (sales / "seeds/reference").mkdir(parents=True)
    (sales / "seeds/reference/countries.yaml").write_text(
        "kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  code: STRING\n"
    )
    (sales / "seeds/reference/countries.csv").write_text("code\nAU\n")
    write_model(
        project, "sales/models/gold/finance/monthly/x.yaml", "SELECT * FROM sales.silver.countries"
    )

    compiled = mason(project, "compile", "--env", "dev")

    assert compiled.exit_code == 0, compiled.output
    assert "STREAMING TABLE dev_sales.silver.orders" in compiled.stdout
    assert "dev_sales.silver.countries" in compiled.stdout
    assert "MATERIALIZED VIEW dev_sales.gold.x" in compiled.stdout


SAME_NAME = {
    "sources": ("sources/a/orders.yaml", "sources/b/orders.yaml"),
    "seeds": ("seeds/a/countries.yaml", "seeds/countries.yaml"),
    "models": ("models/gold/a/x.yaml", "models/gold/b/x.yaml"),
}


@pytest.mark.parametrize("kind", SAME_NAME)
def test_two_files_with_one_name_in_a_domains_layer_fail_naming_both(project: Path, kind: str):
    first, second = SAME_NAME[kind]
    sales = project / "domains/sales"
    for path in (first, second):
        (sales / path).parent.mkdir(parents=True, exist_ok=True)
        if kind == "models":
            write_model(project, f"sales/{path}", "SELECT * FROM sales.silver.orders")
        elif kind == "seeds":
            (sales / path).write_text(
                "kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  code: STRING\n"
            )
            (sales / path).with_suffix(".csv").write_text("code\nAU\n")
        else:
            (sales / path).write_text((sales / "sources/orders.yaml").read_text())
    (sales / "sources/orders.yaml").unlink()

    [failure] = [d for d in diagnostics(project) if d["rule"] == "MSN120"]

    assert f"domains/sales/{first}" in failure["message"]
    assert f"domains/sales/{second}" in failure["message"]
    assert mason(project, "compile").exit_code == 1


def test_one_name_in_two_model_layers_is_two_tables(project: Path):
    set_model_layers(project, "gold", "marts")
    write_model(project, "sales/models/gold/x.yaml", "SELECT * FROM sales.silver.orders")
    write_model(project, "sales/models/marts/x.yaml", "SELECT * FROM sales.gold.x")

    passes(project)


def bundle(project: Path) -> dict:
    result = mason(project, "compile")
    assert result.exit_code == 0, result.output
    return yaml.safe_load((project / "build/databricks.yaml").read_text())


def test_a_model_layer_adds_a_schema_not_a_pipeline(project: Path):
    set_model_layers(project, "gold", "marts")
    write_model(project, "sales/models/marts/x.yaml", "SELECT * FROM sales.gold.dim_date")

    package = bundle(project)

    assert sorted(package["resources"]["pipelines"]) == ["sales_gold", "sales_ingest"]
    assert package["targets"]["dev"]["variables"]["schema_sales_marts"] == "marts"


def test_the_order_of_model_layers_changes_nothing(project: Path):
    write_model(project, "sales/models/marts/x.yaml", "SELECT * FROM sales.gold.dim_date")
    set_model_layers(project, "gold", "marts")
    first = bundle(project)
    (project / PLATFORM).write_text(
        (project / PLATFORM).read_text().replace("[gold, marts]", "[marts, gold]")
    )

    assert bundle(project) == first


def test_a_layer_catalogs_project_with_a_domain_per_source_system_validates_and_compiles(
    tmp_path: Path,
):
    assert (
        runner.invoke(app, ["init", str(tmp_path), "--naming-style", "layer-catalogs"]).exit_code
        == 0
    )
    platform = tmp_path / PLATFORM
    platform.write_text(platform.read_text().replace("  - sales\n", "  - sales\n  - salesforce\n"))
    sources = tmp_path / "domains/salesforce/sources"
    sources.mkdir(parents=True)
    (sources / "accounts.yaml").write_text(
        "kind: source\nversion: 1\npath: /Volumes/{env}_bronze/salesforce/landing/accounts\n"
        "format: json\nsilver:\n  export: true\n"
    )
    write_model(
        tmp_path, "sales/models/gold/dim_account.yaml", "SELECT * FROM salesforce.silver.accounts"
    )

    passes(tmp_path)
    compiled = mason(tmp_path, "compile", "--env", "dev")
    assert compiled.exit_code == 0, compiled.output
    assert "STREAMING TABLE dev_silver.salesforce.accounts" in compiled.stdout
    assert "MATERIALIZED VIEW dev_gold.sales.dim_account" in compiled.stdout
    assert "FROM dev_silver.salesforce.accounts" in compiled.stdout
