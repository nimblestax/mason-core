"""`mason init [FOLDER]` creates the project folder, and never overwrites a project."""

import json
from pathlib import Path

from typer.testing import CliRunner

from mason import cli
from mason.cli import app
from mason.diagnostics import RULES

runner = CliRunner()

FCT_ORDERS = "domains/sales/models/gold/fct_orders.sql"


def init(*args: str, input: str | None = None):
    return runner.invoke(app, ["init", *args], input=input)


def test_a_second_init_in_the_same_folder_fails_and_changes_nothing(tmp_path: Path):
    assert init(str(tmp_path), "--naming-style", "layer-catalogs").exit_code == 0
    (tmp_path / FCT_ORDERS).write_text("SELECT 1 AS edited\n")
    contract = (tmp_path / "mason.platform.yaml").read_text()

    result = init(str(tmp_path))

    assert result.exit_code == 2
    assert "MSN909" in result.stdout
    assert "Fix: " in result.stdout
    assert (tmp_path / FCT_ORDERS).read_text() == "SELECT 1 AS edited\n"
    assert (tmp_path / "mason.platform.yaml").read_text() == contract


def test_init_creates_the_folder_and_its_parents_and_names_the_project_after_it(tmp_path: Path):
    folder = tmp_path / "work" / "sales-platform"

    result = init(str(folder), "--json")

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["result"]["project"] == str(folder)
    assert "name: sales_platform\n" in (folder / "mason.platform.yaml").read_text()


def test_with_no_folder_init_writes_into_the_current_folder(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert init().exit_code == 0

    assert (tmp_path / "mason.platform.yaml").exists()


def test_a_folder_with_other_files_in_it_still_works(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# Sales platform\n")

    assert init(str(tmp_path)).exit_code == 0

    assert (tmp_path / "README.md").read_text() == "# Sales platform\n"
    assert (tmp_path / "mason.platform.yaml").exists()


def test_the_refusal_is_one_envelope_with_json(tmp_path: Path):
    assert init(str(tmp_path)).exit_code == 0

    result = init(str(tmp_path), "--json")

    assert result.exit_code == 2
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "mason.init/1"
    assert envelope["ok"] is False
    [diagnostic] = envelope["diagnostics"]
    assert diagnostic["rule"] == "MSN909"
    assert diagnostic["name"] == RULES["MSN909"].name
    assert diagnostic["file"] == "mason.platform.yaml"
    assert diagnostic["fix"]


def test_init_has_no_project_option(tmp_path: Path):
    assert init("--project", str(tmp_path)).exit_code == 2


def test_the_command_page_shows_the_folder_as_optional():
    page = Path(__file__).parent.parent / "docs/reference/commands/init.md"

    assert "$ mason init [<folder>] [OPTIONS]" in page.read_text()


def test_at_a_terminal_the_refusal_comes_before_the_question(tmp_path: Path, monkeypatch):
    assert init(str(tmp_path)).exit_code == 0
    monkeypatch.setattr(cli, "_at_a_terminal", lambda: True)

    result = init(str(tmp_path), input="layer-catalogs\n")

    assert result.exit_code == 2
    assert "Naming Style" not in result.output
