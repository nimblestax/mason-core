"""Reads follow a fixed build order: each Domain's silver is private unless it's Exported, nobody
reads another Domain's gold, and the Shared Domain's gold is read by every Domain."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import app

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The project `mason init` writes, with `finance` and `shared` Domains beside `sales`."""
    assert mason(tmp_path, "init").exit_code == 0
    platform = tmp_path / "mason.platform.yaml"
    platform.write_text(
        platform.read_text().replace("  - sales\n", "  - sales\n  - finance\n  - shared\n")
    )
    return tmp_path


def write_source(project: Path, domain: str, name: str, silver: str = "") -> None:
    folder = project / "domains" / domain / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(
        f"kind: source\nversion: 1\npath: /Volumes/{{env}}_{domain}/bronze/landing/{name}\n"
        f"format: json\n{silver}"
    )


def write_model(project: Path, domain: str, name: str, query: str) -> str:
    folder = project / "domains" / domain / "models"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(f"kind: model\nversion: 1\nsql: {name}.sql\n")
    (folder / f"{name}.sql").write_text(query)
    return f"domains/{domain}/models/{name}.sql"


def failures(project: Path) -> list[dict]:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 1, result.output
    return json.loads(result.stdout)["diagnostics"]


def assert_passes(project: Path) -> None:
    result = mason(project, "validate", "--json")
    assert result.exit_code == 0, result.output


def test_reading_another_domains_gold_fails_and_its_exported_silver_passes(project: Path):
    write_source(project, "finance", "invoices", "silver:\n  export: true\n")
    write_model(project, "finance", "fct_invoices", "SELECT * FROM finance.silver.invoices")
    file = write_model(project, "sales", "fct_billed", "SELECT * FROM finance.gold.fct_invoices")

    [failure] = failures(project)

    assert failure["rule"] == "MSN209"
    assert failure["name"] == "cross-domain-read"
    assert failure["file"] == file
    assert failure["line"] == 1
    assert "finance.gold.fct_invoices" in failure["message"]
    assert "finance.silver.invoices" not in failure["message"]
    assert failure["fix"]

    write_model(project, "sales", "fct_billed", "SELECT * FROM finance.silver.invoices")

    assert_passes(project)


def test_every_domain_reads_the_shared_domains_gold(project: Path):
    write_model(project, "shared", "dim_country", "SELECT 'NZ' AS code")
    write_model(project, "sales", "fct_by_country", "SELECT * FROM shared.gold.dim_country")
    write_model(project, "finance", "fct_by_country", "SELECT * FROM shared.gold.dim_country")

    assert_passes(project)


def test_the_shared_domain_does_not_read_a_domains_gold(project: Path):
    file = write_model(project, "shared", "dim_order", "SELECT * FROM sales.gold.fct_orders")

    [failure] = failures(project)

    assert failure["rule"] == "MSN209"
    assert failure["file"] == file
    assert "sales.gold.fct_orders" in failure["message"]


def test_another_domains_private_silver_fails_naming_export_as_the_fix(project: Path):
    write_source(project, "finance", "invoices")
    file = write_model(project, "sales", "fct_billed", "SELECT * FROM finance.silver.invoices")

    [failure] = failures(project)

    assert failure["rule"] == "MSN209"
    assert failure["file"] == file
    assert "finance.silver.invoices" in failure["message"]
    assert "hasn't Exported" in failure["message"]
    assert "export: true" in failure["fix"]


def test_another_domains_gold_fails_naming_the_shared_domain_as_the_fix(project: Path):
    write_model(project, "finance", "fct_invoices", "SELECT 1 AS id")
    write_model(project, "sales", "fct_billed", "SELECT * FROM finance.gold.fct_invoices")

    [failure] = failures(project)

    assert "Nobody reads another Domain's gold" in failure["message"]
    assert "Shared Domain" in failure["fix"]


def test_the_shared_domain_reads_exported_silver_from_any_domain_and_its_own(project: Path):
    write_source(project, "finance", "invoices", "silver:\n  export: true\n")
    write_source(project, "shared", "countries")
    write_model(
        project,
        "shared",
        "dim_customer",
        "SELECT * FROM sales.silver.orders_exported"
        " JOIN finance.silver.invoices USING (id) JOIN shared.silver.countries USING (code)",
    )
    write_source(project, "sales", "orders_exported", "silver:\n  export: true\n")

    assert_passes(project)


def test_the_shared_domain_does_not_read_a_domains_private_silver(project: Path):
    write_model(project, "shared", "dim_order", "SELECT * FROM sales.silver.orders")

    [failure] = failures(project)

    assert failure["rule"] == "MSN209"
    assert "sales.silver.orders" in failure["message"]


def test_the_shared_domains_silver_is_private_like_any_domains(project: Path):
    write_source(project, "shared", "countries")
    write_model(project, "sales", "fct_by_country", "SELECT * FROM shared.silver.countries")

    [failure] = failures(project)

    assert failure["rule"] == "MSN209"


def test_an_exported_sources_quarantine_table_stays_private(project: Path):
    write_source(
        project,
        "finance",
        "invoices",
        "silver:\n  export: true\n"
        "  expectations:\n    - name: positive\n      expect: amount > 0\n",
    )
    write_model(project, "sales", "fct_rejects", "SELECT * FROM finance.silver.invoices_quarantine")

    [failure] = failures(project)

    assert failure["rule"] == "MSN209"
    assert "finance.silver.invoices_quarantine" in failure["message"]


def write_seed(project: Path, domain: str, name: str, extra: str = "") -> None:
    folder = project / "domains" / domain / "seeds"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.yaml").write_text(
        f"kind: seed\nversion: 1\nfile: {name}.csv\ncolumns:\n  code: STRING\n{extra}"
    )
    (folder / f"{name}.csv").write_text("code\nNZ\n")


def test_another_domains_seed_is_read_only_once_exported(project: Path):
    write_seed(project, "finance", "cost_centres")
    write_model(project, "sales", "fct_costs", "SELECT * FROM finance.silver.cost_centres")

    [failure] = failures(project)
    assert failure["rule"] == "MSN209"

    write_seed(project, "finance", "cost_centres", "export: true\n")

    assert_passes(project)


def test_a_gold_model_reading_its_own_domains_bronze_fails_naming_silver(project: Path):
    file = write_model(project, "sales", "fct_raw", "SELECT *\nFROM sales.bronze.orders")

    [failure] = failures(project)

    assert failure["rule"] == "MSN210"
    assert failure["name"] == "read-against-build-order"
    assert failure["file"] == file
    assert failure["line"] == 2
    assert "sales.bronze.orders" in failure["message"]
    assert "sales.silver.orders" in failure["fix"]


def test_another_domains_bronze_fails_once_against_the_build_order(project: Path):
    write_source(project, "finance", "invoices", "silver:\n  export: true\n")
    write_model(project, "sales", "fct_raw", "SELECT * FROM finance.bronze.invoices")

    [failure] = failures(project)

    assert failure["rule"] == "MSN210"


UPSERT = "silver:\n  keys: [id]\n  sequence_by: updated_at\n"


@pytest.mark.parametrize("scd", ["1", "2"])
def test_a_stream_of_upsert_silver_fails_and_a_batch_read_passes(project: Path, scd: str):
    write_source(project, "sales", "customers", f"{UPSERT}  scd: {scd}\n")
    file = write_model(
        project, "sales", "fct_customers", "SELECT *\nFROM STREAM(sales.silver.customers)"
    )

    [failure] = failures(project)

    assert failure["rule"] == "MSN211"
    assert failure["name"] == "stream-of-upsert-silver"
    assert failure["file"] == file
    assert failure["line"] == 2
    assert "sales.silver.customers" in failure["message"]
    assert "STREAM" in failure["fix"]

    write_model(project, "sales", "fct_customers", "SELECT * FROM sales.silver.customers")

    assert_passes(project)


def test_a_stream_of_append_silver_passes(project: Path):
    write_model(project, "sales", "fct_events", "SELECT * FROM STREAM(sales.silver.orders)")

    assert_passes(project)


def test_a_stream_of_another_domains_exported_upsert_silver_fails(project: Path):
    write_source(project, "finance", "invoices", f"{UPSERT}  export: true\n")
    write_model(
        project, "sales", "fct_billed", "SELECT * FROM STREAM(finance.silver.invoices) AS i"
    )

    [failure] = failures(project)

    assert failure["rule"] == "MSN211"


def test_domains_reading_each_others_gold_fail_on_each_read_not_as_a_loop(project: Path):
    write_model(project, "sales", "fct_a", "SELECT * FROM finance.gold.fct_b")
    write_model(project, "finance", "fct_b", "SELECT * FROM sales.gold.fct_a")

    assert sorted(failure["rule"] for failure in failures(project)) == ["MSN209", "MSN209"]
