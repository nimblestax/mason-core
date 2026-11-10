"""`depends_on:` names reads the parser can't see, and each must appear in the SQL as written."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

MODEL = "domains/sales/models/gold/fct_orders"
# Databricks accepts a watermark, but the parser doesn't, so it can't find the read.
WATERMARKED = (
    "SELECT order_id, amount\n"
    "FROM STREAM(sales.silver.orders) WATERMARK ordered_at DELAY OF INTERVAL 1 MINUTE\n"
)

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def write_model(project: Path, query: str, depends_on: list[str]) -> None:
    (project / f"{MODEL}.sql").write_text(query)
    config = project / f"{MODEL}.yaml"
    names = "".join(f"  - {name}\n" for name in depends_on)
    config.write_text(f"{config.read_text()}depends_on:\n{names}")


def diagnostics(project: Path) -> list[dict]:
    return json.loads(mason(project, "validate", "--json").stdout)["diagnostics"]


def test_a_declared_name_in_the_sql_lets_sql_the_parser_cant_read_validate(project: Path):
    write_model(project, WATERMARKED, ["sales.silver.orders"])

    result = mason(project, "validate", "--json")

    assert result.exit_code == 0, result.output


def test_a_declared_name_missing_from_the_sql_fails_with_its_own_rule(project: Path):
    write_model(project, WATERMARKED, ["sales.silver.orders", "sales.silver.customers"])

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN212"
    assert failure["name"] == "depends-on-not-in-sql"
    assert failure["file"] == f"{MODEL}.yaml"
    assert "sales.silver.customers" in failure["message"]
    assert failure["fix"]


def test_a_declared_name_compiles_to_the_real_table_by_exact_match(project: Path):
    write_model(project, WATERMARKED, ["sales.silver.orders"])

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    assert "FROM STREAM(dev_sales.silver.orders) WATERMARK ordered_at" in result.stdout


@pytest.mark.parametrize(
    ("declared", "rule"),
    [
        ("sales.bronze.orders", "MSN210"),
        ("sales.silver.nope", "MSN201"),
        ("sales.gold.fct_orders", "MSN208"),
    ],
)
def test_a_declared_read_obeys_the_same_rules_as_a_parsed_one(
    project: Path, declared: str, rule: str
):
    query = f"SELECT *\nFROM STREAM({declared}) WATERMARK ordered_at DELAY OF INTERVAL 1 MINUTE\n"
    write_model(project, query, [declared])

    [failure] = diagnostics(project)

    assert failure["rule"] == rule


def test_a_declared_read_of_another_domains_gold_fails(project: Path):
    platform = project / "mason.platform.yaml"
    platform.write_text(platform.read_text().replace("  - sales\n", "  - sales\n  - finance\n"))
    finance = project / "domains/finance/models/gold"
    finance.mkdir(parents=True)
    (finance / "fct_invoices.sql").write_text("SELECT 1 AS id\n")
    (finance / "fct_invoices.yaml").write_text("kind: model\nversion: 1\nsql: fct_invoices.sql\n")
    query = (
        "SELECT *\nFROM STREAM(finance.gold.fct_invoices) WATERMARK t DELAY OF INTERVAL 1 MINUTE\n"
    )
    write_model(project, query, ["finance.gold.fct_invoices"])

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN209"
    assert failure["line"] == 2


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM STREAM(sales.silver.orders_v2) WATERMARK t DELAY OF INTERVAL 1 MINUTE",
        "SELECT * FROM STREAM(Sales.Silver.Orders) WATERMARK t DELAY OF INTERVAL 1 MINUTE",
        "SELECT * FROM STREAM(x.sales.silver.orders) WATERMARK t DELAY OF INTERVAL 1 MINUTE",
    ],
)
def test_only_the_name_exactly_as_declared_counts(project: Path, query: str):
    write_model(project, query, ["sales.silver.orders"])

    rules = {failure["rule"] for failure in diagnostics(project)}

    assert "MSN212" in rules


def test_a_declared_name_also_reads_where_the_parser_can_read_the_sql(project: Path):
    query = "SELECT order_id, 'sales.silver.orders' AS lineage FROM sales.silver.orders"
    write_model(project, query, ["sales.silver.orders"])

    result = mason(project, "compile", "--env", "dev")

    assert result.exit_code == 0, result.output
    assert "'dev_sales.silver.orders' AS lineage FROM dev_sales.silver.orders" in result.stdout


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE sales.silver.orders",
        "INSERT INTO sales.gold.dim_date SELECT * FROM sales.silver.orders",
        "SELECT * FROM sales.silver.orders;\nSELECT * FROM sales.silver.orders",
    ],
)
def test_depends_on_never_lets_through_sql_that_parses_but_isnt_one_query(
    project: Path, query: str
):
    write_model(project, query, ["sales.silver.orders"])

    [failure] = diagnostics(project)

    assert failure["rule"] == "MSN203"
    assert "depends_on" not in failure["fix"]
