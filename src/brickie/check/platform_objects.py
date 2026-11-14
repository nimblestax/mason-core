"""Platform rules. `brickie validate --platform` runs these against one Environment's workspace.

Brickie never creates catalogs or schemas. Whoever owns the platform does, so a missing one fails
here, before a deploy, rather than halfway through one.
"""

from typing import Protocol

from brickie import names
from brickie.diagnostics import Diagnostic, error
from brickie.kinds import platform
from brickie.load.project import Project


class UnityCatalog(Protocol):
    """What the Databricks boundary reports about a workspace's catalogs and schemas."""

    def catalogs(self, host: str) -> set[str]:
        """The catalogs the signed-in identity can see."""
        ...

    def schemas(self, host: str, catalog: str) -> set[str]:
        """The schemas in one catalog the signed-in identity can see."""
        ...


def check(project: Project, env: str, workspace: UnityCatalog) -> list[Diagnostic]:
    host = project.platform.hosts[env]
    catalogs, schemas = names.platform_objects(project.platform, [env])
    present = _lowercase(workspace.catalogs(host))
    diagnostics = []
    for catalog in catalogs:
        needed = [schema for schema in schemas if schema.split(".")[0] == catalog]
        if catalog.lower() not in present:
            diagnostics.append(_missing_catalog(env, host, catalog, needed))
            continue
        found = _lowercase(workspace.schemas(host, catalog))
        diagnostics += [
            _missing_schema(env, host, schema)
            for schema in needed
            if schema.split(".")[1].lower() not in found
        ]
    return diagnostics


def _lowercase(found: set[str]) -> set[str]:
    """Unity Catalog matches names whatever their case."""
    return {name.lower() for name in found}


def _missing_catalog(env: str, host: str, catalog: str, schemas: list[str]) -> Diagnostic:
    listed = ", ".join(f"`{schema}`" for schema in schemas)
    return error(
        "BRK301",
        platform.FILE_NAME,
        f"The catalog `{catalog}` isn't in {env}'s workspace, {host}, or the identity Brickie"
        f" signed in as can't see it. The project's tables in {env} need it.",
        f"Create the catalog `{catalog}` with the schemas {listed}, or grant the identity"
        " `USE CATALOG` on it. Brickie never creates catalogs.",
    )


def _missing_schema(env: str, host: str, schema: str) -> Diagnostic:
    catalog, name = schema.split(".")
    return error(
        "BRK302",
        platform.FILE_NAME,
        f"The schema `{schema}` isn't in {env}'s workspace, {host}, or the identity Brickie"
        f" signed in as can't see it. The project's tables in {env} need it.",
        f"Create the schema `{name}` in the catalog `{catalog}`, or grant the identity"
        " `USE SCHEMA` on it. Brickie never creates schemas.",
    )
