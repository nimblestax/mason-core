"""The contract machines rely on: one envelope, stable rule IDs and three exit codes."""

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason.cli import PASSED_THROUGH, app, every_command
from mason.deploy import pinned_cli
from mason.diagnostics import DOCS, RULES, error
from mason.scaffold import PLACEHOLDER_HOST

runner = CliRunner()


def mason(project: Path, *args: str):
    return runner.invoke(app, [*args, "--project", str(project)])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0
    return tmp_path


def test_validate_prints_an_envelope_with_the_rule_id_and_exits_1(project: Path):
    (project / "domains/sales/models/gold/fct_orders.sql").write_text(
        "SELECT * FROM sales.silver.nope"
    )

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1
    envelope = json.loads(result.stdout)
    assert list(envelope) == ["schema", "mason_version", "ok", "result", "diagnostics"]
    assert envelope["schema"] == "mason.validate/1"
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert list(diagnostic) == [
        "rule",
        "name",
        "severity",
        "file",
        "line",
        "message",
        "fix",
        "docs",
    ]
    assert diagnostic["rule"] == "MSN201"
    assert diagnostic["file"] == "domains/sales/models/gold/fct_orders.sql"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (
            ["init", "kettle"],
            {
                "project": "kettle",
                "naming_style": "domain-catalogs",
                "catalogs": ["dev_sales"],
                "schemas": ["dev_sales.bronze", "dev_sales.silver", "dev_sales.gold"],
                "skills": [
                    ".agents/skills/mason-add-model",
                    ".claude/skills/mason-add-model",
                    ".agents/skills/mason-add-source",
                    ".claude/skills/mason-add-source",
                ],
                "skills_left_alone": [],
                "volumes": ["dev_sales.bronze.landing"],
                "example": None,
                "uploads": [],
            },
        ),
        (["validate"], {}),
        (["compile"], {"package": "build"}),
    ],
)
def test_a_command_reports_its_result_in_the_envelope(
    project: Path, monkeypatch, command: list[str], expected: dict
):
    monkeypatch.chdir(project)

    result = runner.invoke(app, [*command, "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == f"mason.{command[0]}/1"
    assert envelope["ok"] is True
    assert envelope["result"] == expected
    assert envelope["diagnostics"] == []


def test_compile_for_an_environment_returns_the_sql_in_the_envelope(project: Path):
    result = mason(project, "compile", "--env", "dev", "--json")

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["result"]["env"] == "dev"
    assert "dev_sales.gold.fct_orders" in envelope["result"]["sql"]


def test_every_registered_command_has_the_json_option():
    """A new command that doesn't register through the shared wrapper fails here."""
    commands = every_command()
    assert {"init", "validate", "schema", "compile", "deploy", "skills update"} <= set(commands)
    for name, registered in commands.items():
        if name in PASSED_THROUGH:
            continue  # Its arguments, `--json` among them, belong to the CLI it runs.
        options = [option for parameter in registered.params for option in parameter.opts]
        assert "--json" in options, f"`mason {name}` has no --json"


def run_mason(*args: str, databricks: Path) -> subprocess.CompletedProcess:
    """The installed command in its own process, so stdout and stderr are the real ones."""
    executable = Path(sys.executable).with_name("mason")
    environment = {pinned_cli.OVERRIDE: str(databricks)}
    return subprocess.run([executable, *args], capture_output=True, text=True, env=environment)


def fake_databricks(folder: Path, exit_code: int = 0) -> Path:
    """A Databricks CLI that logs to stdout, as the real one does for bundle runs."""
    folder.mkdir()
    script = folder / "databricks"
    script.write_text(
        "#!/bin/sh\n"
        f"[ \"$1\" = --version ] && echo 'Databricks CLI v{pinned_cli.MINIMUM}' && exit 0\n"
        f"echo 'Uploading bundle files'\nexit {exit_code}\n"
    )
    script.chmod(0o755)
    return script


def test_stdout_is_pure_json_while_the_databricks_cli_logs(project: Path, tmp_path_factory):
    databricks = fake_databricks(tmp_path_factory.mktemp("cli") / "bin")

    result = run_mason(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=databricks
    )

    assert result.returncode == 0, result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "mason.deploy/1"
    assert envelope["result"] == {"env": "dev"}
    assert "Uploading bundle files" in result.stderr


def test_a_failing_databricks_command_is_an_environment_error(project: Path, tmp_path_factory):
    databricks = fake_databricks(tmp_path_factory.mktemp("cli") / "bin", exit_code=3)

    result = run_mason(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=databricks
    )

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN904"


def test_a_missing_databricks_cli_is_an_environment_error(project: Path, tmp_path_factory):
    missing = tmp_path_factory.mktemp("empty") / "databricks"

    result = run_mason(
        "deploy", "--env", "dev", "--json", "--project", str(project), databricks=missing
    )

    assert result.returncode == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN903"
    assert pinned_cli.OVERRIDE in diagnostic["fix"]


@pytest.mark.parametrize(
    ("arguments", "schema"),
    [
        (["schema", "--json"], "mason.schema/1"),
        (["validate", "--json", "--nope"], "mason.validate/1"),
        (["init", "--ci", "gitlab", "--json"], "mason.init/1"),
        (["nope", "--json"], "mason.usage/1"),
    ],
)
def test_a_usage_error_is_an_envelope_that_exits_2(arguments: list[str], schema: str):
    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == schema
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN901"
    assert diagnostic["message"]
    assert "--help" in diagnostic["fix"]


def test_a_usage_error_without_json_stays_text_for_a_person():
    result = runner.invoke(app, ["schema"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Missing argument" in result.stderr


@pytest.mark.parametrize("command", ["compile", "deploy"])
def test_an_unknown_environment_is_a_usage_error_naming_the_environments(
    project: Path, command: str
):
    result = mason(project, command, "--env", "staging", "--json")

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN902"
    assert "dev" in diagnostic["fix"]


@pytest.mark.parametrize("as_json", [True, False])
def test_a_crash_keeps_the_exit_code_contract(tmp_path: Path, as_json: bool):
    in_the_way = tmp_path / "a-file"
    in_the_way.write_text("not a folder")
    flags = ["--json"] if as_json else []

    result = runner.invoke(app, ["init", str(in_the_way), *flags])

    assert result.exit_code == 2
    assert "MSN905" in result.stdout
    assert "Traceback" in result.stderr
    assert "Traceback" not in result.stdout
    if as_json:
        assert json.loads(result.stdout)["schema"] == "mason.init/1"


def test_a_project_problem_without_json_stays_text_for_a_person(project: Path):
    (project / "domains/sales/models/gold/fct_orders.sql").write_text(
        "SELECT * FROM sales.silver.nope"
    )

    result = mason(project, "validate")

    assert result.exit_code == 1
    assert "MSN201 domains/sales/models/gold/fct_orders.sql:" in result.stdout
    assert "Fix: " in result.stdout


# Copied by hand on purpose. Editing a line here means a rule ID changed meaning, was removed or
# was reused, which breaks every agent and script that relies on it. Only ever add lines.
REGISTERED_RULES = {
    "MSN101": "missing-kind",
    "MSN102": "unknown-kind",
    "MSN103": "missing-version",
    "MSN104": "unknown-version",
    "MSN105": "wrong-kind",
    "MSN106": "invalid-field",
    "MSN107": "unreadable-config",
    "MSN108": "sql-without-config",
    "MSN109": "missing-sql-file",
    "MSN110": "keys-without-sequence-by",
    "MSN111": "upsert-field-without-keys",
    "MSN112": "missing-seed-file",
    "MSN113": "seed-header-mismatch",
    "MSN114": "seed-row-mismatch",
    "MSN115": "unsupported-seed-type",
    "MSN116": "invalid-expectation",
    "MSN117": "invalid-name",
    "MSN118": "invalid-delete-when",
    "MSN119": "invalid-sequence-by",
    "MSN120": "duplicate-config-file",
    "MSN121": "unlisted-domain-folder",
    "MSN122": "dev-host-missing",
    "MSN123": "two-default-environments",
    "MSN124": "naming-patterns-not-supported",
    "MSN125": "source-layers-fixed",
    "MSN126": "model-layer-named-like-a-source-layer",
    "MSN127": "model-outside-a-layer",
    "MSN129": "skill-version-drift",
    "MSN130": "no-development-environment",
    "MSN131": "two-environments-with-one-role",
    "MSN132": "environment-name-not-an-identifier",
    "MSN201": "unresolved-logical-name",
    "MSN202": "duplicate-table",
    "MSN203": "unparseable-sql",
    "MSN204": "computed-table-name",
    "MSN205": "real-table-name",
    "MSN206": "file-read",
    "MSN207": "raw-string-placeholder",
    "MSN208": "model-cycle",
    "MSN209": "cross-domain-read",
    "MSN210": "read-against-build-order",
    "MSN211": "stream-of-upsert-silver",
    "MSN212": "stream-of-materialized-view",
    "MSN301": "missing-catalog",
    "MSN302": "missing-schema",
    "MSN901": "usage-error",
    "MSN902": "unknown-environment",
    "MSN903": "databricks-cli-missing",
    "MSN904": "databricks-command-failed",
    "MSN905": "unexpected-error",
    "MSN906": "pipeline-column-not-found",
    "MSN907": "expectation-failed",
    "MSN908": "pipeline-failed",
    "MSN909": "project-already-exists",
    "MSN910": "databricks-cli-checksum-mismatch",
    "MSN911": "databricks-cli-unsupported",
    "MSN912": "databricks-cli-download-failed",
    "MSN913": "no-databricks-cli-for-platform",
    "MSN914": "skills-folder-ignored",
    "MSN915": "skill-edited",
    "MSN916": "unknown-example",
}


# Removed before any release, so no project ever saw them. Their IDs are still never reused.
RETIRED_RULES = {"MSN128": "production-shares-a-workspace"}


def test_no_rule_id_is_removed_reused_or_changes_meaning():
    assert {code: rule.name for code, rule in RULES.items()} == REGISTERED_RULES
    assert not RETIRED_RULES.keys() & REGISTERED_RULES.keys()
    assert not set(RETIRED_RULES.values()) & set(REGISTERED_RULES.values())


def test_rule_ids_are_msn_plus_three_digits_with_one_name_each():
    assert all(re.fullmatch(r"MSN\d{3}", rule) for rule in RULES)
    assert len({rule.name for rule in RULES.values()}) == len(RULES)


def test_an_unregistered_rule_can_not_be_reported():
    with pytest.raises(KeyError):
        error("MSN999", "", "A message.", "A fix.")


def replacing(file: str, old: str, new: str) -> Callable[[Path], None]:
    def change(project: Path) -> None:
        path = project / file
        assert old in path.read_text()
        path.write_text(path.read_text().replace(old, new))

    return change


SOURCE = "domains/sales/sources/orders.yaml"
PLATFORM = "mason.platform.yaml"
MODEL = "domains/sales/models/gold/fct_orders"


def seed(column: str, rows: str | None, name: str = "countries") -> Callable[[Path], None]:
    def declare(project: Path) -> None:
        folder = project / "domains/sales/seeds"
        folder.mkdir()
        config = f"kind: seed\nversion: 1\nfile: {name}.csv\ncolumns:\n  {column}\n"
        (folder / f"{name}.yaml").write_text(config)
        if rows is not None:
            (folder / f"{name}.csv").write_text(rows)

    return declare


def read_a_domains_gold_from_shared(project: Path) -> None:
    """A Shared Domain Model reading a Domain's gold, which nobody outside that Domain reads."""
    replacing("mason.platform.yaml", "  - sales\n", "  - sales\n  - shared\n")(project)
    folder = project / "domains/shared/models/gold"
    folder.mkdir(parents=True)
    (folder / "dim_order.yaml").write_text("kind: model\nversion: 1\nsql: dim_order.sql\n")
    (folder / "dim_order.sql").write_text("SELECT * FROM sales.gold.fct_orders")


INVALID_PROJECTS = {
    "MSN101": replacing(SOURCE, "kind: source\n", ""),
    "MSN102": replacing(SOURCE, "kind: source\n", "kind: sauce\n"),
    "MSN103": replacing(SOURCE, "version: 1\n", ""),
    "MSN104": replacing(SOURCE, "version: 1\n", "version: 2\n"),
    "MSN105": replacing(SOURCE, "kind: source\n", "kind: model\n"),
    "MSN106": replacing(SOURCE, "format: json\n", "format: 7\n"),
    "MSN107": lambda project: (project / SOURCE).write_text("just a string"),
    "MSN108": lambda project: (project / f"{MODEL}.yaml").unlink(),
    "MSN109": lambda project: (project / f"{MODEL}.sql").unlink(),
    "MSN110": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  keys: [order_id]\n"),
    "MSN111": replacing(SOURCE, "format: json\n", "format: json\nsilver:\n  scd: 2\n"),
    "MSN112": seed("code: STRING", None),
    "MSN113": seed("code: STRING", "nope\nAU\n"),
    "MSN114": seed("code: INT", "code\nAU\n"),
    "MSN115": seed("code: VARCAHR", "code\nAU\n"),
    "MSN116": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  expectations:\n    - name: bad\n      expect: amount >\n",
    ),
    "MSN117": seed("code: STRING", "code\nAU\n", name="vat-rates"),
    "MSN118": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n"
        "  delete_when: op =\n",
    ),
    "MSN119": replacing(
        SOURCE,
        "format: json\n",
        "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at DESC\n",
    ),
    "MSN120": lambda project: (project / SOURCE.replace(".yaml", ".yml")).write_text(
        (project / SOURCE).read_text()
    ),
    "MSN121": lambda project: (project / "domains/hr").mkdir(),
    "MSN122": replacing(PLATFORM, f"    host: {PLACEHOLDER_HOST}\n", ""),
    "MSN123": replacing(
        PLATFORM,
        "    role: development\n",
        "    role: development\n    default: true\n  prod:\n    default: true\n",
    ),
    "MSN124": replacing(PLATFORM, "  style: domain-catalogs\n", '  catalog: "{env}"\n'),
    "MSN125": lambda project: (project / PLATFORM).write_text(
        "kind: platform\nversion: 1\nname: shop\nenvironments:\n  dev:\n"
        f"    host: {PLACEHOLDER_HOST}\n"
        'naming:\n  catalog: "{env}_{domain}"\n  schema: "{layer}"\n'
        "  layers:\n    sources: [bronze, curated]\n    models: [gold]\ndomains:\n  - sales\n"
    ),
    "MSN126": replacing(PLATFORM, "models: [gold]", "models: [gold, silver]"),
    "MSN127": lambda project: (project / "domains/sales/models/x.sql").write_text("SELECT 1"),
    "MSN130": replacing(PLATFORM, "    role: development\n", ""),
    "MSN131": replacing(
        PLATFORM,
        "    role: development\n",
        "    role: development\n  test:\n    role: development\n",
    ),
    "MSN132": replacing(
        PLATFORM, "    role: development\n", "    role: development\n  prd-1: {}\n"
    ),
    "MSN201": lambda project: (project / f"{MODEL}.sql").write_text("SELECT * FROM a.b.c"),
    "MSN202": seed("code: STRING", "code\nAU\n", name="orders"),
    "MSN203": lambda project: (project / f"{MODEL}.sql").write_text("SELECT FROM WHERE"),
    "MSN204": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM IDENTIFIER(:table)"
    ),
    "MSN205": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM dev_sales.silver.orders"
    ),
    "MSN206": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM read_files('/Volumes/x')"
    ),
    "MSN207": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT r'${env}' AS x FROM sales.silver.orders"
    ),
    "MSN208": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.gold.fct_orders"
    ),
    "MSN209": lambda project: read_a_domains_gold_from_shared(project),
    "MSN210": lambda project: (project / f"{MODEL}.sql").write_text(
        "SELECT * FROM sales.bronze.orders"
    ),
    "MSN211": lambda project: (
        replacing(
            SOURCE,
            "format: json\n",
            "format: json\nsilver:\n  keys: [order_id]\n  sequence_by: updated_at\n",
        )(project),
        (project / f"{MODEL}.sql").write_text("SELECT * FROM STREAM(sales.silver.orders)"),
    ),
    "MSN212": lambda project: (
        seed("code: STRING", "code\nAU\n")(project),
        (project / f"{MODEL}.sql").write_text("SELECT * FROM STREAM(sales.silver.countries)"),
    ),
}


@pytest.mark.parametrize(("rule", "break_project"), INVALID_PROJECTS.items())
def test_every_project_rule_reports_a_message_and_a_fix_and_exits_1(
    project: Path, rule: str, break_project: Callable[[Path], None]
):
    break_project(project)

    result = mason(project, "validate", "--json")

    assert result.exit_code == 1, result.output
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == rule
    assert diagnostic["name"] == RULES[rule].name
    assert diagnostic["severity"] == "error"
    assert diagnostic["message"]
    assert diagnostic["fix"]
    assert diagnostic["docs"] == DOCS


def test_a_new_rule_must_be_tested_here():
    """The tests above, and the refresh failure, init folder, pinned CLI, platform check,
    skills and Kettle tests, cover these by name. A new rule joins one."""
    usage_and_environment = {"MSN901", "MSN902", "MSN903", "MSN904", "MSN905", "MSN909"}
    refresh_failures = {"MSN906", "MSN907", "MSN908"}
    pinned_cli_failures = {"MSN910", "MSN911", "MSN912", "MSN913"}
    platform_checks = {"MSN301", "MSN302"}
    skills = {"MSN129", "MSN914", "MSN915"}
    examples = {"MSN916"}

    assert set(RULES) == (
        set(INVALID_PROJECTS)
        | usage_and_environment
        | refresh_failures
        | pinned_cli_failures
        | platform_checks
        | skills
        | examples
    )


def test_the_docs_state_every_exit_code_and_every_rule():
    docs = (Path(__file__).parent.parent / "docs/reference/json-output.md").read_text()

    assert "| 0 | Clean" in docs
    assert "| 1 | Rule failures" in docs
    assert "| 2 | Usage or environment error" in docs
    for code, rule in RULES.items():
        assert f"| [`{code}`](rules/{code.lower()}.md) | `{rule.name}` |" in docs


def test_help_states_the_exit_codes():
    result = runner.invoke(app, ["--help"])

    assert "0 clean, 1 rule failures, 2 usage or environment error" in result.stdout
