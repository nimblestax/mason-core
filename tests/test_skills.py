"""Mason Skills: `mason init` installs them, `mason validate` warns on drift, and
`mason skills update` refreshes them without losing local edits."""

import json
import os
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mason import skills
from mason.cli import app

runner = CliRunner()

SKILL_FOLDERS = (".agents/skills", ".claude/skills")


def files_under(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def test_init_beside_an_existing_claude_folder_adds_only_mason_folders(tmp_path: Path):
    claude = tmp_path / ".claude"
    (claude / "skills/my-skill").mkdir(parents=True)
    (claude / "skills/my-skill/SKILL.md").write_text("---\nname: my-skill\n---\nMine.\n")
    (claude / "settings.json").write_text('{"model": "opus"}\n')
    before = files_under(claude)

    result = runner.invoke(app, ["init", str(tmp_path)])

    assert result.exit_code == 0, result.output
    after = files_under(claude)
    added = {path for path in after if path not in before}
    assert added, "init wrote no skills"
    assert all(path.startswith("skills/mason-") for path in added)
    assert {path: after[path] for path in before} == before


def test_init_leaves_an_existing_mason_skill_folder_alone(tmp_path: Path):
    mine = tmp_path / ".claude/skills/mason-add-source"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("My own steps.\n")

    result = runner.invoke(app, ["init", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.output
    assert files_under(mine) == {"SKILL.md": b"My own steps.\n"}
    assert (tmp_path / ".agents/skills/mason-add-source/SKILL.md").is_file()
    created = json.loads(result.stdout)["result"]
    assert ".claude/skills/mason-add-source" in created["skills_left_alone"]
    assert ".claude/skills/mason-add-source" not in created["skills"]
    assert ".agents/skills/mason-add-source" in created["skills"]


def test_init_with_skills_none_writes_no_skills(tmp_path: Path):
    result = runner.invoke(app, ["init", str(tmp_path), "--skills", "none"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".agents").exists()
    assert not (tmp_path / ".claude").exists()


# The fields the Agent Skills standard defines, so every coding agent reads the same skill.
STANDARD_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def front_matter(skill: Path) -> dict:
    return yaml.safe_load(skill.read_text().split("---\n")[1])


def test_init_writes_identical_copies_using_only_standard_fields(tmp_path: Path):
    assert runner.invoke(app, ["init", str(tmp_path)]).exit_code == 0

    main, claude = (files_under(tmp_path / folder) for folder in SKILL_FOLDERS)
    assert main == claude
    assert set(main) == {f"{name}/SKILL.md" for name in skills.shipped()}
    for path in main:
        fields = front_matter(tmp_path / SKILL_FOLDERS[0] / path)
        assert set(fields) <= STANDARD_FIELDS, path
        assert fields["name"] == path.split("/")[0]
        assert fields["description"]
        assert all(isinstance(value, str) for value in fields["metadata"].values())
        assert fields["metadata"]["mason-version"] == version("mason-databricks")


def test_no_skill_runs_mason_deploy():
    for name, text in skills.shipped().items():
        assert "mason deploy" not in text, name


SOURCE_SKILL = ".agents/skills/mason-add-source/SKILL.md"


def written_by(project: Path, skill: str, mason_version: str) -> None:
    path = project / skill
    current = f'mason-version: "{version("mason-databricks")}"'
    path.write_text(path.read_text().replace(current, f'mason-version: "{mason_version}"'))


def test_validate_warns_when_a_skill_is_from_another_mason_and_still_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    written_by(tmp_path, SOURCE_SKILL, "0.0.1")

    result = runner.invoke(app, ["validate", "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    [found] = envelope["diagnostics"]
    assert (found["rule"], found["severity"], found["file"]) == ("MSN129", "warning", SOURCE_SKILL)
    assert "0.0.1" in found["message"]
    assert "mason skills update" in found["fix"]


def test_validate_prints_a_drift_warning_beside_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    written_by(tmp_path, SOURCE_SKILL, "0.0.1")

    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 0
    assert f"MSN129 {SOURCE_SKILL} (warning): " in result.stdout
    assert result.stdout.rstrip().endswith("Valid.")


def test_validate_says_nothing_of_skills_written_by_this_mason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0

    result = runner.invoke(app, ["validate", "--json"])

    assert json.loads(result.stdout)["diagnostics"] == []


@pytest.fixture
def outside_any_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Git hook, such as pre-commit, sets `GIT_DIR` and others. Left set, `git init` here and
    the `git check-ignore` Mason runs would act on the repo being committed to."""
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)


def git_repo_ignoring(folder: Path, pattern: str) -> None:
    subprocess.run(["git", "init", "-q", str(folder)], check=True)
    # Not `.gitignore`, which `mason init` writes its own of.
    (folder / ".git/info/exclude").write_text(f"{pattern}\n")


@pytest.mark.usefixtures("outside_any_repo")
def test_init_warns_when_git_ignores_the_claude_folder(tmp_path: Path):
    git_repo_ignoring(tmp_path, ".claude/")

    result = runner.invoke(app, ["init", str(tmp_path), "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    [found] = envelope["diagnostics"]
    assert (found["rule"], found["severity"], found["file"]) == (
        "MSN914",
        "warning",
        ".claude/skills",
    )


@pytest.mark.usefixtures("outside_any_repo")
def test_init_gives_no_warning_when_git_keeps_the_skills(tmp_path: Path):
    git_repo_ignoring(tmp_path, "build/")

    result = runner.invoke(app, ["init", str(tmp_path), "--json"])

    assert json.loads(result.stdout)["diagnostics"] == []


def initialised(folder: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Path:
    monkeypatch.chdir(folder)
    assert runner.invoke(app, ["init", *args]).exit_code == 0
    return folder


def test_skills_update_refreshes_both_copies_of_skills_from_another_mason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = initialised(tmp_path, monkeypatch)
    for folder in SKILL_FOLDERS:
        written_by(project, f"{folder}/mason-add-source/SKILL.md", "0.0.1")
    (project / ".claude/skills/my-skill").mkdir()
    (project / ".claude/skills/my-skill/SKILL.md").write_text("Mine.\n")

    result = runner.invoke(app, ["skills", "update", "--json"])

    assert result.exit_code == 0, result.output
    envelope = json.loads(result.stdout)
    assert envelope["schema"] == "mason.skills.update/1"
    assert sorted(envelope["result"]["skills"]) == [
        ".agents/skills/mason-add-source",
        ".claude/skills/mason-add-source",
    ]
    for folder in SKILL_FOLDERS:
        installed = (project / folder / "mason-add-source/SKILL.md").read_text()
        assert installed == skills.shipped()["mason-add-source"]
    assert (project / ".claude/skills/my-skill/SKILL.md").read_text() == "Mine.\n"
    assert json.loads(runner.invoke(app, ["validate", "--json"]).stdout)["diagnostics"] == []


def test_skills_update_writes_skills_a_project_never_had(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = initialised(tmp_path, monkeypatch, "--skills", "none")

    result = runner.invoke(app, ["skills", "update"])

    assert result.exit_code == 0, result.output
    main, claude = (files_under(project / folder) for folder in SKILL_FOLDERS)
    assert main == claude
    assert set(main) == {f"{name}/SKILL.md" for name in skills.shipped()}


def edit(project: Path, skill: str, extra: str) -> str:
    path = project / skill
    path.write_text(path.read_text() + extra)
    return path.read_text()


def test_skills_update_stops_on_a_local_edit_shows_it_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = initialised(tmp_path, monkeypatch)
    edited = edit(project, ".claude/skills/mason-add-model/SKILL.md", "6. Our own step.\n")
    written_by(project, SOURCE_SKILL, "0.0.1")
    old = (project / SOURCE_SKILL).read_text()

    result = runner.invoke(app, ["skills", "update", "--json"])

    assert result.exit_code == 2, result.output
    envelope = json.loads(result.stdout)
    [found] = envelope["diagnostics"]
    assert (found["rule"], found["file"]) == ("MSN915", ".claude/skills/mason-add-model/SKILL.md")
    assert "-6. Our own step." in found["message"]
    assert "--force" in found["fix"]
    assert (project / ".claude/skills/mason-add-model/SKILL.md").read_text() == edited
    assert (project / SOURCE_SKILL).read_text() == old


def test_skills_update_with_force_replaces_a_local_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = initialised(tmp_path, monkeypatch)
    edit(project, ".claude/skills/mason-add-model/SKILL.md", "6. Our own step.\n")

    result = runner.invoke(app, ["skills", "update", "--force"])

    assert result.exit_code == 0, result.output
    installed = (project / ".claude/skills/mason-add-model/SKILL.md").read_text()
    assert installed == skills.shipped()["mason-add-model"]


def test_a_skill_checked_out_with_windows_line_endings_is_not_an_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project = initialised(tmp_path, monkeypatch)
    path = project / SOURCE_SKILL
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    assert runner.invoke(app, ["skills", "update"]).exit_code == 0


def test_skills_update_outside_a_project_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["skills", "update", "--json"])

    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["diagnostics"][0]["file"] == "mason.platform.yaml"
    assert list(tmp_path.iterdir()) == []
