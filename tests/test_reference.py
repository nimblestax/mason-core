import json
import re
import shlex
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
import typer
from test_docs import front_matter
from typer.testing import CliRunner

from mason import reference
from mason.cli import GROUPS, PASSED_THROUGH, app, every_command
from mason.diagnostics import EXIT_CODES
from mason.kinds import KINDS, latest_schema
from mason.registry import RULES, SERIES, Example

DOCS = Path(__file__).parent.parent / "docs"


def generated_pages(docs: Path) -> dict[str, str]:
    pages = {page.relative_to(docs).as_posix(): page.read_text() for page in docs.rglob("*.md")}
    return {name: text for name, text in pages.items() if front_matter(text).get("generated")}


def test_every_rule_gets_a_page_that_says_it_is_generated_and_by_which_mason(tmp_path: Path):
    reference.write(tmp_path)

    for code in RULES:
        page = front_matter((tmp_path / f"reference/rules/{code.lower()}.md").read_text())
        assert page["title"].startswith(code)
        assert page["description"]
        assert page["generated"] is True
        assert page["mason_version"] == version("mason-databricks")


def test_every_kind_gets_a_page_that_says_it_is_generated_and_by_which_mason(tmp_path: Path):
    reference.write(tmp_path)

    for kind in KINDS:
        page = front_matter((tmp_path / f"reference/kinds/{kind}.md").read_text())
        assert page["title"]
        assert page["description"] == latest_schema(kind)[1]["description"]
        assert page["generated"] is True
        assert page["mason_version"] == version("mason-databricks")


def field_rows(page: str) -> list[list[str]]:
    """The cells of each row of a Kind page's field table, after its two header lines."""
    table = page.split("## Fields\n\n")[1].split("\n\n")[0].splitlines()[2:]
    return [[cell.strip() for cell in row.strip("|").split(" | ")] for row in table]


def test_a_kind_page_lists_every_field_with_its_type_whether_required_and_default(
    tmp_path: Path,
):
    reference.write(tmp_path)

    rows = field_rows((tmp_path / "reference/kinds/source.md").read_text())
    formats = "one of `avro`, `binaryFile`, `csv`, `json`, `orc`, `parquet`, `text`, `xml`"
    actions = "one of `warn`, `quarantine`, `fail`"
    assert [row[:4] for row in rows] == [
        ["`kind`", "`source`", "yes", ""],
        ["`version`", "`1`", "yes", ""],
        ["`path`", "string", "yes", ""],
        ["`format`", formats, "yes", ""],
        ["`silver`", "object", "no", "`{}`"],
        ["`silver.keys`", "list of string", "no", "`null`"],
        ["`silver.sequence_by`", "string", "no", "`null`"],
        ["`silver.scd`", "one of `1`, `2`", "no", "`1`"],
        ["`silver.delete_when`", "string", "no", "`null`"],
        ["`silver.export`", "boolean", "no", "`false`"],
        ["`silver.expectations`", "list of object", "no", "`[]`"],
        ["`silver.expectations[].name`", "string", "yes", ""],
        ["`silver.expectations[].expect`", "string", "yes", ""],
        ["`silver.expectations[].action`", actions, "no", "`quarantine`"],
    ]


def schema_fields(schema: dict, defs: dict) -> list[tuple[str, str, str]]:
    """Each field's (name, required, description), nested objects' fields after their own."""
    fields = []
    for name, field in schema["properties"].items():
        required = "yes" if name in schema.get("required", []) else "no"
        fields.append((name, required, field["description"]))
        inner = field.get("$ref") or field.get("items", {}).get("$ref")
        # An optional object is `anyOf` its own schema and null.
        for choice in field.get("anyOf", []):
            inner = inner or choice.get("$ref")
        if isinstance(field.get("additionalProperties"), dict):
            inner = field["additionalProperties"].get("$ref")
        if inner:
            fields += schema_fields(defs[inner.split("/")[-1]], defs)
    return fields


@pytest.mark.parametrize("kind", KINDS)
def test_a_kind_page_and_mason_schema_never_disagree(tmp_path: Path, kind: str):
    reference.write(tmp_path)
    printed = json.loads(CliRunner().invoke(app, ["schema", kind, "--json"]).stdout)
    schema = printed["result"]["json_schema"]

    rows = field_rows((tmp_path / f"reference/kinds/{kind}.md").read_text())

    listed = [(row[0].strip("`").split(".")[-1].removesuffix("[]"), row[2], row[4]) for row in rows]
    assert listed == schema_fields(schema, schema.get("$defs", {}))


def test_the_committed_reference_is_what_mason_generates(tmp_path: Path):
    reference.write(tmp_path)

    assert generated_pages(DOCS) == generated_pages(tmp_path), "Run `just docs` and commit."


def test_every_rule_has_a_committed_page():
    missing = [
        code for code in RULES if not (DOCS / f"reference/rules/{code.lower()}.md").is_file()
    ]

    assert missing == [], "Run `just docs` and commit."


def test_a_rule_page_says_what_it_checks_why_an_example_that_fails_and_the_fix(tmp_path: Path):
    reference.write(tmp_path)

    rule = RULES["MSN201"]
    page = (tmp_path / "reference/rules/msn201.md").read_text()
    assert f"## What it checks\n\n{rule.checks}\n" in page
    assert f"## Why\n\n{rule.why}\n" in page
    for path, text in rule.example.files.items():
        assert f"`{path}`" in page
        assert f"```sql\n{text}```\n" in page
    assert f"## Fix\n\n{rule.fix}\n" in page


# An example that needs a machine in some state, such as with no Databricks CLI, says so in `when`.
RUNNABLE = {code: rule.example for code, rule in RULES.items() if not rule.example.when}


@pytest.mark.parametrize(("code", "example"), RUNNABLE.items())
def test_every_example_fails_with_its_own_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str, example: Example
):
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    for path, text in example.files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    command = shlex.split(example.command or "mason validate")[1:]

    result = runner.invoke(app, [*command, "--json"])

    assert [found["rule"] for found in json.loads(result.stdout)["diagnostics"]] == [code]


def test_a_rule_page_links_the_principle_behind_it_where_there_is_one(tmp_path: Path):
    reference.write(tmp_path)

    enforced = (tmp_path / "reference/rules/msn201.md").read_text()
    assert "(https://nimblestax.com/way/code-names-tables-logically)" in enforced
    assert "nimblestax.com/way" not in (tmp_path / "reference/rules/msn203.md").read_text()


# The Way's principles as nimblestax.com publishes them.
# A renamed principle fails here, not as a dead link.
PUBLISHED_PRINCIPLES = {
    "config-over-code",
    "bronze-is-append-only",
    "silver-is-typed-and-conformed",
    "no-row-disappears-silently",
    "data-flows-one-way",
    "code-names-tables-logically",
    "every-change-goes-through-a-pull-request",
    "prod-is-a-promotion",
    "nothing-is-destroyed-by-accident",
}


@pytest.mark.parametrize("code", [code for code, rule in RULES.items() if rule.principle])
def test_a_rule_links_a_principle_the_way_still_publishes(code: str):
    principle = RULES[code].principle
    assert principle is not None
    assert principle.slug in PUBLISHED_PRINCIPLES


def commands() -> dict[str, Any]:
    return every_command()


def test_every_command_gets_a_page_listing_its_options_and_exit_codes(tmp_path: Path):
    reference.write(tmp_path)

    for name, registered in commands().items():
        file, _, section = reference.page_link(name).partition("#")
        text = whole = (tmp_path / f"reference/commands/{file}").read_text()
        page = front_matter(text)
        assert page["generated"] is True
        if section:  # A subcommand is a section of its group's page.
            text = text.split(f"\n## {section}\n")[1].split("\n## ")[0]
            assert text.startswith(f"\n{registered.help}\n")
        else:
            assert page["title"] == f"mason {name}"
            assert page["description"] == registered.help
        if name in PASSED_THROUGH:
            continue  # Its arguments and exit codes are the Databricks CLI's.
        for parameter in registered.params:
            assert f"`{parameter.opts[0]}`" in text, f"{name} {parameter.opts[0]}"
        for code, meaning in EXIT_CODES.items():
            assert f"| {code} | {meaning} |" in whole


def test_the_databricks_page_says_its_arguments_and_exit_code_are_the_clis(tmp_path: Path):
    reference.write(tmp_path)

    text = (tmp_path / "reference/commands/databricks.md").read_text()
    assert "$ mason databricks <arguments>" in text
    assert "exits with its exit code" in text
    assert "## JSON result" not in text


@pytest.mark.parametrize(
    "command",
    [
        ["init"],
        ["validate"],
        ["schema", "source"],
        ["compile"],
        ["compile", "--env", "dev"],
        ["skills", "update"],
    ],
)
def test_a_command_page_documents_every_field_of_its_json_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: list[str]
):
    reference.write(tmp_path / "docs")
    monkeypatch.chdir(tmp_path)
    assert CliRunner().invoke(app, ["init"]).exit_code == 0

    envelope = json.loads(CliRunner().invoke(app, [*command, "--json"]).stdout)

    page = command[0]
    text = (tmp_path / f"docs/reference/commands/{page}.md").read_text()
    assert f"`{envelope['schema']}`" in text
    for field in envelope["result"]:
        assert f"| `{field}` |" in text, field


def test_the_json_page_documents_the_envelope_and_links_every_command_and_the_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    reference.write(tmp_path / "docs")
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(app, ["init"])
    (tmp_path / "domains/sales/models/gold/fct_orders.sql").write_text("SELECT * FROM a.b.c")

    envelope = json.loads(CliRunner().invoke(app, ["validate", "--json"]).stdout)

    text = (tmp_path / "docs/reference/json-output.md").read_text()
    page = front_matter(text)
    assert page["generated"] is True
    assert page["redirects"] == ["json-output"]
    for field in [*envelope, *envelope["diagnostics"][0]]:
        assert f"| `{field}` |" in text, field
    for name in commands():
        assert f"(commands/{reference.page_link(name)})" in text, name
    assert "(rules/index.md)" in text
    assert "\n## Rule IDs\n" in text


def test_generated_pages_say_nothing_private(tmp_path: Path):
    reference.write(tmp_path)

    for name, text in generated_pages(tmp_path).items():
        assert not re.search(r"\bADRs?\b|nimblestax-internal|\bclients?\b", text), name


def test_the_platform_page_lists_each_naming_style_as_a_choice(tmp_path: Path):
    reference.write(tmp_path)

    rows = field_rows((tmp_path / "reference/kinds/platform.md").read_text())
    [style] = [row for row in rows if row[0] == "`naming.style`"]
    assert style[1:3] == [
        "one of `domain-catalogs`, `layer-catalogs`, `environment-catalogs`",
        "yes",
    ]


def index_rows(page: str) -> list[tuple[str, str, str]]:
    """Each Rule row of the Rules index, as (series heading, code, linked page)."""
    rows, heading = [], ""
    for line in page.splitlines():
        if line.startswith("## "):
            heading = line.removeprefix("## ")
        found = re.match(r"\| \[`(MSN\d{3})`\]\(([^)]+)\) \|", line)
        if found:
            rows.append((heading, found[1], found[2]))
    return rows


def test_the_rules_index_lists_every_rule_once_under_its_series_linking_its_page(
    tmp_path: Path,
):
    reference.write(tmp_path)

    index = (tmp_path / "reference/rules/index.md").read_text()
    assert front_matter(index)["generated"] is True
    rows = index_rows(index)
    assert sorted(code for _, code, _ in rows) == sorted(RULES)
    for heading, code, page in rows:
        assert heading == f"`{code[:4]}xx` {SERIES[code[:4]]}", code
        assert (tmp_path / "reference/rules" / page).is_file(), page


def test_every_rule_belongs_to_a_series_with_a_heading():
    assert {code[:4] for code in RULES} <= set(SERIES)


@pytest.mark.parametrize("group", GROUPS)
def test_a_command_group_gets_one_page_with_a_section_per_subcommand(tmp_path: Path, group: str):
    reference.write(tmp_path)

    text = (tmp_path / f"reference/commands/{group}.md").read_text()
    page = front_matter(text)
    registered: Any = typer.main.get_command(app)
    assert page["title"] == f"mason {group}"
    assert page["description"] == registered.commands[group].help
    for inner in registered.commands[group].commands:
        assert f"\n## {inner}\n" in text, inner
        assert f"$ mason {group} {inner}" in text, inner
        assert not (tmp_path / f"reference/commands/{group}-{inner}.md").exists()


def test_writing_the_reference_twice_gives_the_same_pages(tmp_path: Path):
    reference.write(tmp_path / "once")
    reference.write(tmp_path / "twice")
    reference.write(tmp_path / "twice")

    assert generated_pages(tmp_path / "twice") == generated_pages(tmp_path / "once")
