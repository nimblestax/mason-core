"""A Gold Model: a dataset built from SQL that reads Logical Names."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from mason.diagnostics import Diagnostic, error
from mason.kinds.base import (
    CONFIG_SUFFIXES,
    STRICT,
    ExactInteger,
    InDomain,
    config_files,
    unique,
)

KIND = "model"
FOLDER = "models"

# Three identifiers joined by dots, as a Logical Name is written in SQL.
WRITTEN_LOGICAL_NAME = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*){2}$"


class ModelV1(InDomain):
    """A dataset built from a SQL file that reads Logical Names."""

    model_config = ConfigDict(**STRICT, title="Mason Gold Model")

    kind: Literal["model"] = Field(description="The Kind of this file.")
    version: Annotated[Literal[1], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    sql: str = Field(
        pattern=r"^[^/\\]+\.sql$", description="The SQL file, in the same folder as this file."
    )
    depends_on: list[Annotated[str, Field(pattern=WRITTEN_LOGICAL_NAME)]] = Field(
        default_factory=list,
        json_schema_extra={"uniqueItems": True},
        description="Logical Names the SQL reads where Mason can't parse it. Each must appear in"
        " the SQL exactly as written here, and Mason replaces it there.",
    )

    @field_validator("depends_on")
    @classmethod
    def _depends_on_is_unique(cls, depends_on: list[str]) -> list[str]:
        return unique(depends_on, "name in `depends_on`")

    def layer(self, model_layers: tuple[str, ...]) -> str:
        """The first folder under `models/` names the Layer. A file directly in `models/` is in
        the last model Layer."""
        return self.folders[0] if self.folders else model_layers[-1]

    @property
    def sql_file(self) -> Path:
        return self.config_file.parent / self.sql

    @property
    def query(self) -> str:
        return self.sql_file.read_text()


VERSIONS: dict[int, type[BaseModel]] = {1: ModelV1}
Model = ModelV1

# `UPGRADES[n]` turns version n into version n + 1.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {}


def problems(root: Path, folder: Path, models: list[Model]) -> list[Diagnostic]:
    """A Model whose SQL file is missing, and a SQL file that no Model names."""
    missing = [
        _missing_sql(_relative(root, model.config_file), model.sql)
        for model in models
        if not model.sql_file.exists()
    ]
    unnamed = [
        _sql_without_config(_relative(root, sql_file), sql_file.stem)
        for sql_file in sorted(folder.glob("*.sql"))
        if not _has_config_beside(sql_file) and not _is_named(sql_file)
    ]
    return missing + unnamed


def generate(model: Model, target: str, sql: str) -> str:
    return f"CREATE OR REFRESH MATERIALIZED VIEW {target} AS\n{sql}"


def _has_config_beside(sql_file: Path) -> bool:
    return any(sql_file.with_suffix(suffix).exists() for suffix in CONFIG_SUFFIXES)


def _is_named(sql_file: Path) -> bool:
    """Whether any config file beside it names it, even one that's invalid in other ways."""
    return any(_names(file, sql_file.name) for file in config_files(sql_file.parent))


def _names(file: Path, sql: str) -> bool:
    try:
        content = yaml.safe_load(file.read_text())
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return False
    return isinstance(content, dict) and content.get("sql") == sql


def _relative(root: Path, file: Path) -> str:
    return file.relative_to(root).as_posix()


def _sql_without_config(file: str, stem: str) -> Diagnostic:
    return error(
        "MSN108",
        file,
        "This SQL file has no config file beside it.",
        f"Add `{stem}.yaml` beside it with `kind: model`, `version: 1` and `sql: {stem}.sql`.",
    )


def _missing_sql(file: str, sql: str) -> Diagnostic:
    return error(
        "MSN109",
        file,
        f"`{sql}` doesn't exist beside this file.",
        "Correct `sql`, or add the SQL file to the same folder.",
    )
