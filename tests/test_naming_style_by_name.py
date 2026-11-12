"""The Platform Contract keeps the Naming Style by name, and version 1 patterns upgrade to it."""

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason import names
from mason.cli import app
from mason.kinds.platform import PlatformV2
from mason.load.project import load

PLATFORM = "mason.platform.yaml"

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def version_1(catalog: str, schema: str, sources: str = "[bronze, silver]") -> str:
    return (
        "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
        "    host: https://dev.example.com\n  prod:\n    host: https://prod.example.com\n"
        f'naming:\n  catalog: "{catalog}"\n  schema: "{schema}"\n'
        f"  layers:\n    sources: {sources}\n    models: [gold]\ndomains:\n  - sales\n"
    )


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def test_a_version_1_contract_with_a_styles_patterns_upgrades_to_that_style(project: Path):
    (project / PLATFORM).write_text(version_1("{env}_{domain}", "{layer}"))

    assert load(project).platform.naming.style == "domain-catalogs"
    compiled = mason(project, "compile", "--env", "prod")
    assert compiled.exit_code == 0, compiled.output
    assert "STREAMING TABLE prod_sales.silver.orders" in compiled.stdout


@pytest.mark.parametrize(
    ("catalog", "schema", "closest"),
    [
        ("{env}", "{layer}", "domain-catalogs"),  # Every Domain's silver in one schema.
        ("{domain}", "{layer}", "domain-catalogs"),  # dev and prod in one table.
        ("acme_{env}_{layer}", "{domain}", "layer-catalogs"),
        ("{env}", "{layer}_{domain}", "environment-catalogs"),
    ],
)
def test_a_version_1_contract_with_other_patterns_fails_naming_the_closest_style(
    project: Path, catalog: str, schema: str, closest: str
):
    (project / PLATFORM).write_text(version_1(catalog, schema))

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN124"
    assert diagnostic["file"] == PLATFORM
    assert f"The closest is `{closest}`" in diagnostic["message"]
    assert "Custom patterns aren't supported yet" in diagnostic["message"]
    assert f"style: {closest}" in diagnostic["fix"]


@pytest.mark.parametrize("sources", ["[bronze, curated]", "[raw, silver]"])
def test_a_version_1_contract_with_renamed_source_layers_fails_pointing_to_a_model_layer(
    project: Path, sources: str
):
    (project / PLATFORM).write_text(version_1("{env}_{domain}", "{layer}", sources))

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN125"
    assert "always bronze and silver" in diagnostic["message"]
    assert "naming.layers.models" in diagnostic["fix"]


def version_2(naming: str) -> str:
    return (
        "kind: platform\nversion: 2\nname: shop\nenvironments:\n  dev:\n"
        "    host: https://dev.example.com\n    role: development\n"
        f"naming:\n{naming}  layers:\n    models: [gold]\n"
        "domains:\n  - sales\n"
    )


@pytest.mark.parametrize("style", ["domain-catalogs", "layer-catalogs", "environment-catalogs"])
def test_a_version_2_contract_takes_each_style(project: Path, style: str):
    (project / PLATFORM).write_text(version_2(f"  style: {style}\n"))

    assert load(project).platform.naming.style == style


@pytest.mark.parametrize("style", ["custom", "Domain-Catalogs", "single-catalog"])
def test_a_version_2_contract_with_any_other_style_fails_naming_the_field(
    project: Path, style: str
):
    (project / PLATFORM).write_text(version_2(f"  style: {style}\n"))

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN106"
    assert diagnostic["message"].startswith("naming.style: ")
    assert "domain-catalogs" in diagnostic["message"]


@pytest.mark.parametrize(
    "naming",
    [
        '  style: domain-catalogs\n  catalog: "{env}_{domain}"\n',
        '  catalog: "{env}_{domain}"\n  schema: "{layer}"\n',
        '  schema: "{layer}"\n',
    ],
)
def test_a_version_2_contract_with_patterns_fails_with_msn124(project: Path, naming: str):
    (project / PLATFORM).write_text(version_2(naming))

    [diagnostic] = failures(project)

    assert diagnostic["rule"] == "MSN124"
    assert "`style`" in diagnostic["fix"]


@pytest.mark.parametrize("style", ["domain-catalogs", "layer-catalogs", "environment-catalogs"])
def test_init_writes_the_style_by_name_under_a_comment_listing_every_style(
    tmp_path: Path, style: str
):
    assert runner.invoke(app, ["init", str(tmp_path), "--naming-style", style]).exit_code == 0

    text = (tmp_path / PLATFORM).read_text()
    assert yaml.safe_load(text)["version"] == 2
    assert yaml.safe_load(text)["naming"] == {"style": style, "layers": {"models": ["gold"]}}
    comment = text.split("naming:\n", 1)[1].split("  style:", 1)[0]
    for listed, table in [
        ("domain-catalogs", "prod_sales.silver.orders"),
        ("layer-catalogs", "prod_silver.sales.orders"),
        ("environment-catalogs", "prod.sales_silver.orders"),
    ]:
        assert listed in comment and table in comment
    assert "https://nimblestax.com/docs/concepts/naming" in comment
    assert "default" not in comment  # It describes the choices, not the one picked.


def contract(style: str) -> PlatformV2:
    return PlatformV2.model_validate(
        {
            "kind": "platform",
            "version": 2,
            "name": "shop",
            "environments": {
                "dev": {"host": "https://dev.example.com", "role": "development"},
                "prd": {},
            },
            "naming": {"style": style, "layers": {"models": ["marts", "serving"]}},
            "domains": ["sales", "finance"],
        }
    )


@pytest.mark.parametrize(
    ("style", "catalog", "schema"),
    [
        ("domain-catalogs", "{env}_{domain}", "{layer}"),
        ("layer-catalogs", "{env}_{layer}", "{domain}"),
        ("environment-catalogs", "{env}", "{domain}_{layer}"),
    ],
)
def test_each_style_gives_every_environment_domain_and_layer_its_own_schema(
    style: str, catalog: str, schema: str
):
    catalogs, schemas = names.platform_objects(contract(style))

    pairs = [
        (env, domain, layer)
        for env in ("dev", "prd")
        for domain in ("sales", "finance")
        for layer in ("bronze", "silver", "marts", "serving")
    ]
    expected = [
        f"{catalog.format(env=e, domain=d, layer=lay)}.{schema.format(env=e, domain=d, layer=lay)}"
        for e, d, lay in pairs
    ]
    assert schemas == expected
    assert len(set(schemas)) == len(pairs)
    assert set(catalogs) == {name.split(".")[0] for name in expected}


@pytest.mark.parametrize(
    ("style", "real"),
    [
        ("domain-catalogs", "prd_finance.silver.invoices"),
        ("layer-catalogs", "prd_silver.finance.invoices"),
        ("environment-catalogs", "prd.finance_silver.invoices"),
    ],
)
def test_a_real_name_in_any_style_points_back_to_its_own_domain(
    project: Path, style: str, real: str
):
    text = version_2(f"  style: {style}\n")
    text = text.replace("domains:\n  - sales\n", "domains:\n  - sales\n  - finance\n")
    (project / PLATFORM).write_text(text.replace("naming:", "  prd: {}\nnaming:"))

    found = names.logical_name_for(load(project), names.LogicalName(*real.split(".")))

    assert found == names.LogicalName("finance", "silver", "invoices")
