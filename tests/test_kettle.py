"""Kettle, the fictional tea shop every docs page draws its examples from."""

import json
import subprocess
import zipfile
from importlib.resources import files
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason import cli
from mason.cli import app
from mason.names import NAMING_STYLES

runner = CliRunner()
KETTLE = Path(str(files("mason") / "examples" / "kettle"))


def init_kettle(folder: Path, *args: str):
    return runner.invoke(app, ["init", "--example", "kettle", str(folder), *args])


@pytest.mark.parametrize("style", NAMING_STYLES)
def test_kettle_is_a_valid_project_under_every_naming_style(tmp_path: Path, style: str):
    assert init_kettle(tmp_path).exit_code == 0
    contract = tmp_path / "mason.platform.yaml"
    contract.write_text(contract.read_text().replace("style: domain-catalogs", f"style: {style}"))

    validated = runner.invoke(app, ["validate", "--project", str(tmp_path), "--json"])

    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.stdout)["diagnostics"] == []


def test_init_writes_the_day_folders_and_prints_what_to_create_and_how_to_upload(tmp_path: Path):
    result = init_kettle(tmp_path)

    assert result.exit_code == 0, result.output
    for day in ("day-1", "day-2"):
        assert sorted(p.name for p in (tmp_path / "data" / day).iterdir()) == [
            "customers",
            "orders",
            "product_prices",
        ]
    assert "  Volumes:\n    dev_sales.bronze.landing\n" in result.stdout
    assert (
        "  mason databricks fs cp --recursive data/day-1/orders"
        " dbfs:/Volumes/dev_sales/bronze/landing/orders\n"
    ) in result.stdout


def test_init_writes_kettle_exactly_as_it_ships(tmp_path: Path):
    result = init_kettle(tmp_path, "--json")

    assert json.loads(result.stdout)["result"]["example"] == "kettle"
    for shipped in KETTLE.rglob("*"):
        if shipped.is_file():
            relative = shipped.relative_to(KETTLE).as_posix()
            written = tmp_path / (".gitignore" if relative == "gitignore" else relative)
            assert written.read_text() == shipped.read_text(), relative


def test_an_example_takes_no_naming_style(tmp_path: Path):
    result = init_kettle(tmp_path, "--naming-style", "layer-catalogs", "--json")

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN901"
    assert not (tmp_path / "mason.platform.yaml").exists()


def test_at_a_terminal_an_example_asks_no_naming_style(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)

    result = init_kettle(tmp_path)

    assert result.exit_code == 0, result.output
    assert "Where should tables live?" not in result.output


def test_the_host_given_is_written_into_the_platform_contract(tmp_path: Path):
    init_kettle(tmp_path, "--host", "https://kettle.cloud.databricks.com")

    assert (
        "host: https://kettle.cloud.databricks.com\n"
        in (tmp_path / "mason.platform.yaml").read_text()
    )


def test_an_unknown_example_fails_with_a_rule_that_lists_the_examples(tmp_path: Path):
    result = runner.invoke(app, ["init", "--example", "teapot", str(tmp_path), "--json"])

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN916"
    assert "kettle" in diagnostic["fix"]
    assert not (tmp_path / "mason.platform.yaml").exists()


def rows(day: str, source: str) -> list[dict]:
    folder = KETTLE / "data" / day / source
    return [json.loads(line) for file in sorted(folder.glob("*.json")) for line in file.open()]


def silver(source: str) -> dict:
    config = yaml.safe_load((KETTLE / f"domains/sales/sources/{source}.yaml").read_text())
    return config.get("silver", {})


def test_day_two_appends_new_orders_and_one_breaks_an_expectation():
    assert not silver("orders").get("keys"), "orders is the append Source"
    first = {order["order_id"] for order in rows("day-1", "orders")}
    second = rows("day-2", "orders")

    assert second and first.isdisjoint(order["order_id"] for order in second)
    [rule] = silver("orders")["expectations"]
    assert rule["expect"] == "customer_id IS NOT NULL"
    assert [order["order_id"] for order in second if order["customer_id"] is None] != []


def test_day_two_moves_a_customer_and_deletes_another():
    settings = silver("customers")
    assert (settings["keys"], settings["scd"]) == (["customer_id"], 2)
    assert settings["delete_when"] == "operation = 'DELETE'"
    before = {row["customer_id"]: row for row in rows("day-1", "customers")}
    changes = rows("day-2", "customers")

    moved = [
        row
        for row in changes
        if row["operation"] != "DELETE"
        and row["customer_id"] in before
        and row["city"] != before[row["customer_id"]]["city"]
        and row["updated_at"] > before[row["customer_id"]]["updated_at"]
    ]
    deleted = [
        row for row in changes if row["operation"] == "DELETE" and row["customer_id"] in before
    ]
    assert len(moved) == 1
    assert len(deleted) == 1


def test_day_two_changes_a_price():
    before = {row["product_id"]: row["price"] for row in rows("day-1", "product_prices")}
    [change] = rows("day-2", "product_prices")

    assert change["price"] != before[change["product_id"]]


def test_the_built_wheel_contains_all_of_kettle(tmp_path: Path):
    root = Path(__file__).parent.parent
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(root)],
        check=True,
        capture_output=True,
    )
    [wheel] = tmp_path.glob("*.whl")

    shipped = {name for name in zipfile.ZipFile(wheel).namelist() if "/examples/kettle/" in name}
    expected = {
        f"mason/examples/kettle/{file.relative_to(KETTLE).as_posix()}"
        for file in KETTLE.rglob("*")
        if file.is_file()
    }
    assert expected <= shipped
    assert "mason/examples/kettle/data/day-2/orders/orders-day-2.json" in shipped
