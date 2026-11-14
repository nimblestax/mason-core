"""A Gold Model's SQL decides what it is: one that reads `STREAM(...)` is a streaming table, and
any other is a materialized view, which nothing may stream from."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from brickie.cli import app

runner = CliRunner()


def brickie(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The project `brickie init` writes, which has append silver `sales.silver.orders`."""
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def write_model(project: Path, name: str, query: str) -> str:
    folder = project / "domains/sales/models/gold"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(f"kind: model\nversion: 1\nsql: {name}.sql\n")
    (folder / f"{name}.sql").write_text(query)
    return f"domains/sales/models/gold/{name}.sql"


def compiled(project: Path) -> str:
    result = brickie(project, "compile", "--env", "dev")
    assert result.exit_code == 0, result.output
    return result.stdout


def test_a_gold_model_reading_a_stream_compiles_to_a_streaming_table(project: Path):
    write_model(project, "fct_events", "SELECT * FROM STREAM(sales.silver.orders)")
    write_model(project, "fct_totals", "SELECT * FROM sales.silver.orders")

    code = compiled(project)

    assert "CREATE OR REFRESH STREAMING TABLE dev_sales.gold.fct_events AS\n" in code
    assert "CREATE OR REFRESH MATERIALIZED VIEW dev_sales.gold.fct_totals AS\n" in code


def failures(project: Path) -> list[dict]:
    result = brickie(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def assert_passes(project: Path) -> None:
    result = brickie(project, "validate", "--json")
    assert result.exit_code == 0, result.output


def write_seed(project: Path) -> None:
    folder = project / "domains/sales/seeds"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "countries.yaml").write_text(
        "kind: seed\nversion: 1\nfile: countries.csv\ncolumns:\n  code: STRING\n"
    )
    (folder / "countries.csv").write_text("code\nGB\n")


def test_a_stream_of_a_seed_fails(project: Path):
    write_seed(project)
    file = write_model(project, "fct_countries", "SELECT *\nFROM STREAM(sales.silver.countries)")

    [failure] = failures(project)

    assert failure["rule"] == "BRK212"
    assert failure["name"] == "stream-of-materialized-view"
    assert failure["file"] == file
    assert failure["line"] == 2
    assert "sales.silver.countries" in failure["message"]
    assert "STREAM" in failure["fix"]


def test_a_stream_of_a_gold_model_that_doesnt_stream_fails(project: Path):
    write_model(project, "fct_orders", "SELECT * FROM sales.silver.orders")
    write_model(project, "fct_late", "SELECT * FROM STREAM(sales.gold.fct_orders)")

    [failure] = failures(project)

    assert failure["rule"] == "BRK212"
    assert "sales.gold.fct_orders" in failure["message"]


def test_a_stream_of_a_gold_model_that_streams_passes(project: Path):
    write_model(project, "fct_orders", "SELECT * FROM STREAM(sales.silver.orders)")
    write_model(project, "fct_late", "SELECT * FROM STREAM(sales.gold.fct_orders)")

    assert_passes(project)
    assert "STREAMING TABLE dev_sales.gold.fct_late" in compiled(project)


def test_a_stream_of_a_quarantine_table_passes(project: Path):
    source = project / "domains/sales/sources/orders.yaml"
    source.write_text(
        source.read_text()
        + "silver:\n  expectations:\n    - name: has_id\n      expect: id IS NOT NULL\n"
    )
    write_model(project, "fct_rejected", "SELECT * FROM STREAM(sales.silver.orders_quarantine)")

    assert_passes(project)


def test_a_stream_static_join_is_a_streaming_table(project: Path):
    write_seed(project)
    write_model(
        project,
        "fct_events",
        "SELECT * FROM STREAM(sales.silver.orders) AS o\n"
        "JOIN sales.silver.countries AS c ON o.country = c.code",
    )

    assert_passes(project)
    assert "STREAMING TABLE dev_sales.gold.fct_events" in compiled(project)
