"""Brickie Skills: written into a project as plain copies in each folder coding agents read."""

import difflib
import hashlib
import re
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path

import yaml

from brickie.diagnostics import USAGE_OR_ENVIRONMENT, Diagnostic, Failure, error, warning

# `.agents/skills/` is the main copy. Claude Code reads only `.claude/skills/`, so it gets an
# identical copy. Copies, not symlinks, so they work on Windows.
FOLDERS = (Path(".agents/skills"), Path(".claude/skills"))
SKILL_FILE = "SKILL.md"

# A skill records the Brickie that wrote it, and a digest of the rest of its text. The digest
# leaves out these two lines, so a skill an older Brickie wrote, and nobody edited, still matches.
BRICKIE_LINES = re.compile(r"^  brickie-(version|digest): .*\n", re.MULTILINE)


def shipped() -> dict[str, str]:
    """Each Brickie Skill's name, and its SKILL.md as this Brickie writes it."""
    templates = files("brickie") / "templates" / "skills"
    return {
        folder.name: _render((folder / SKILL_FILE).read_text())
        for folder in sorted(templates.iterdir(), key=lambda entry: entry.name)
        if folder.is_dir()
    }


def _render(template: str) -> str:
    text = template.replace("BRICKIE_VERSION", _brickie_version())
    return text.replace("BRICKIE_DIGEST", _digest(text))


def _digest(text: str) -> str:
    """Of text read with `read_text`, which reads Windows line endings as `\\n`, so a checkout
    with them isn't an edit."""
    return hashlib.sha256(BRICKIE_LINES.sub("", text).encode()).hexdigest()


@dataclass(frozen=True)
class Installed:
    written: list[str]
    left_alone: list[str]


def install(root: Path) -> Installed:
    """Writes each Brickie Skill into each folder, leaving a skill folder that exists alone."""
    installed = Installed([], [])
    for name, text in shipped().items():
        for folder in FOLDERS:
            skill = folder / name
            if (root / skill).exists():
                installed.left_alone.append(skill.as_posix())
                continue
            (root / skill).mkdir(parents=True)
            (root / skill / SKILL_FILE).write_text(text)
            installed.written.append(skill.as_posix())
    return installed


def ignored(root: Path) -> list[Diagnostic]:
    """A warning for each skills folder Git ignores, whose skills would never be committed."""
    warnings = []
    for folder in FOLDERS:
        installed = [folder / name / SKILL_FILE for name in shipped()]
        if any(_git_ignores(root, path) for path in installed if (root / path).is_file()):
            warnings.append(
                warning(
                    "BRK914",
                    folder.as_posix(),
                    f"Git ignores `{folder.as_posix()}/`, so the Brickie Skills in it won't be"
                    " committed.",
                    f"Stop ignoring `{folder.as_posix()}/`, or add `!{folder.as_posix()}/` to"
                    " `.gitignore`, then commit the skills.",
                )
            )
    return warnings


def _git_ignores(root: Path, path: Path) -> bool:
    """Outside a Git repo, or with no Git installed, nothing is ignored."""
    try:
        checked = subprocess.run(
            ["git", "check-ignore", "--quiet", path.as_posix()], cwd=root, capture_output=True
        )
    except FileNotFoundError:
        return False
    return checked.returncode == 0


def drift(root: Path) -> list[Diagnostic]:
    """A warning for each Brickie Skill written by another Brickie than the one installed."""
    installed = _brickie_version()
    warnings = []
    for folder in FOLDERS:
        for name in shipped():
            path = folder / name / SKILL_FILE
            if not (root / path).is_file():
                continue  # Not installed, as with `--skills none`.
            written_by = _recorded_version((root / path).read_text())
            if written_by != installed:
                warnings.append(_drifted(path.as_posix(), name, written_by, installed))
    return warnings


def _recorded_version(text: str) -> str | None:
    return _recorded(text, "brickie-version")


def _recorded(text: str, field: str) -> str | None:
    """A value a SKILL.md's front matter records under `metadata`, or None if it has none."""
    try:
        fields = yaml.safe_load(text.split("---\n")[1])
        return str(fields["metadata"][field])
    except (IndexError, KeyError, TypeError, yaml.YAMLError):
        return None


def update(root: Path, force: bool) -> list[str]:
    """Refreshes both copies of each Brickie Skill, and returns the skill folders it wrote.

    It stops before writing anything if a skill was edited, unless `force` is set, so no edit
    is lost without a word.
    """
    stale = {}
    edits = []
    for name, text in shipped().items():
        for folder in FOLDERS:
            path = folder / name / SKILL_FILE
            local = (root / path).read_text() if (root / path).is_file() else None
            if local == text:
                continue
            if local is not None and _edited(local) and not force:
                edits.append(_edit(path.as_posix(), local, text))
            stale[path] = text
    if edits:
        raise Failure(edits, USAGE_OR_ENVIRONMENT)
    for path, text in stale.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    return sorted(path.parent.as_posix() for path in stale)


def _edited(text: str) -> bool:
    return _recorded(text, "brickie-digest") != _digest(text)


def _edit(file: str, local: str, text: str) -> Diagnostic:
    diff = "".join(
        difflib.unified_diff(
            local.splitlines(keepends=True),
            text.splitlines(keepends=True),
            fromfile=f"{file} (yours)",
            tofile=f"{file} (Brickie {_brickie_version()})",
        )
    )
    return error(
        "BRK915",
        file,
        "This skill was edited since Brickie wrote it, so updating it would lose the edit:"
        f"\n{diff}",
        "Move your edit into a skill of your own, outside the `brickie-*` folders, then run"
        " `brickie skills update` again. To replace the edit, run `brickie skills update --force`.",
    )


def _drifted(file: str, name: str, written_by: str | None, installed: str) -> Diagnostic:
    by = f"Brickie {written_by}" if written_by else "no recorded version of Brickie"
    return warning(
        "BRK129",
        file,
        f"`{name}` was written by {by}, but Brickie {installed} is installed.",
        "Run `brickie skills update` to refresh both copies of each skill, and commit them.",
    )


def _brickie_version() -> str:
    return version("brickie-core")
