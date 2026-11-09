"""`mason init`: writes a working project from the packaged templates."""

import json
import re
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from mason.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error
from mason.kinds import KINDS, json_schemas, platform

PLACEHOLDER_HOST = "https://your-workspace.cloud.databricks.com"
SCHEMA_FOLDER = Path(".mason/schemas")

# Each Naming Style's catalog and schema patterns. Only the patterns are written out.
NAMING_STYLES = {
    "domain-catalogs": ("{env}_{domain}", "{layer}"),
    "layer-catalogs": ("{env}_{layer}", "{domain}"),
    "environment-catalogs": ("{env}", "{domain}_{layer}"),
}

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


def write_project(root: Path, host: str, ci: str, naming_style: str) -> None:
    name = re.sub(r"\W+", "_", root.resolve().name).strip("_").lower()
    catalog, schema = NAMING_STYLES[naming_style]
    # The starter Source reads a volume in the sales Domain's bronze, wherever the style puts it.
    bronze = {"env": "{env}", "domain": "sales", "layer": "bronze"}
    path = f"/Volumes/{catalog.format(**bronze)}/{schema.format(**bronze)}/landing/orders"
    values = {"host": host, "name": name, "catalog": catalog, "schema": schema, "path": path}
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
