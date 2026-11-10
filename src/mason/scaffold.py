"""`mason init`: writes a working project from the packaged templates."""

import json
import re
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from mason import names
from mason.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error
from mason.kinds import KINDS, json_schemas, platform

PLACEHOLDER_HOST = "https://your-workspace.cloud.databricks.com"
SCHEMA_FOLDER = Path(".mason/schemas")

# Templates that take values. The rest are copied as they are.
FILLED_IN = {"mason.platform.yaml", "orders.yaml"}


def refuse_existing_project(root: Path) -> None:
    """Writing over a project would lose its Platform Contract and every edited starter file."""
    if (root / platform.FILE_NAME).exists():
        found = error(
            "MSN909",
            platform.FILE_NAME,
            f"{root} already holds a Mason project.",
            "Run `mason init` in another folder, or give it one, as `mason init <folder>`.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)


def require_project(root: Path) -> None:
    """For a command that writes into a project, so it never writes into another folder."""
    if not (root / platform.FILE_NAME).is_file():
        found = error(
            "MSN107",
            platform.FILE_NAME,
            f"{root} holds no Mason project, so there's no `{platform.FILE_NAME}` to read.",
            "Run the command in a project's folder, or give it one with `--project <folder>`.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)


def write_project(root: Path, host: str, ci: str, naming_style: str) -> None:
    name = re.sub(r"\W+", "_", root.resolve().name).strip("_").lower()
    # The starter Source reads a volume in the sales Domain's bronze, wherever the style puts it.
    catalog, schema = names.real_names(naming_style, "{env}", "sales", "bronze")
    path = f"/Volumes/{catalog}/{schema}/landing/orders"
    # Every style, so the comment stays true whichever one the file names.
    styles = "\n".join(
        f"  #   {style:<22}{names.example_table(style)}" for style in names.NAMING_STYLES
    )
    values = {"host": host, "name": name, "style": naming_style, "styles": styles, "path": path}
    templates = files("mason") / "templates"
    _copy(templates / "project", root, values)
    _copy(templates / "ci" / ci, root, {})
    _write_schemas(root)


def _write_schemas(root: Path) -> None:
    """A copy in the project, so editors check config offline and before any release."""
    folder = root / SCHEMA_FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        for number, schema in json_schemas(kind).items():
            (folder / f"{kind}.v{number}.json").write_text(json.dumps(schema, indent=2) + "\n")


def _copy(template: Traversable, target: Path, values: dict[str, str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in template.iterdir():
        if entry.is_dir():
            _copy(entry, target / entry.name, values)
            continue
        text = entry.read_text()
        if entry.name in FILLED_IN:
            text = text.format(**values)
        destination = ".gitignore" if entry.name == "gitignore" else entry.name
        (target / destination).write_text(
            text.replace("MASON_VERSION", version("mason-databricks"))
        )
