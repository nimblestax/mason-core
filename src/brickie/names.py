"""Name mapping: the only module that builds a real table name."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from brickie.statements import escaped

if TYPE_CHECKING:
    # Only for annotations, because the platform Kind reads the Naming Styles from here.
    from brickie.kinds.platform import Platform
    from brickie.kinds.source import Source
    from brickie.load.project import Project

PLACEHOLDER = re.compile(r"\$\{(\w+)\}")

# Each Naming Style's catalog and schema patterns, in the order `brickie init` offers them.
NAMING_STYLES = {
    "domain-catalogs": ("{env}_{domain}", "{layer}"),
    "layer-catalogs": ("{env}_{layer}", "{domain}"),
    "environment-catalogs": ("{env}", "{domain}_{layer}"),
}


def real_names(style: str, env: str, domain: str, layer: str) -> tuple[str, str]:
    """The catalog and schema that hold one Environment's tables for a Domain and Layer."""
    catalog, schema = NAMING_STYLES[style]
    parts = {"env": env, "domain": domain, "layer": layer}
    return catalog.format(**parts), schema.format(**parts)


def example_table(style: str) -> str:
    """What `sales.silver.orders` is in prod under a Naming Style."""
    catalog, schema = real_names(style, "prod", "sales", "silver")
    return f"{catalog}.{schema}.orders"


def style_for(catalog: str, schema: str) -> str | None:
    """The Naming Style with exactly these patterns, if there is one."""
    for style, patterns in NAMING_STYLES.items():
        if patterns == (catalog, schema):
            return style
    return None


def closest_style(catalog: str, schema: str) -> str:
    """The style that puts the most placeholders where these patterns do, the first on a tie."""

    def shared(style: str) -> int:
        style_catalog, style_schema = NAMING_STYLES[style]
        return sum(
            (placeholder in catalog and placeholder in style_catalog)
            + (placeholder in schema and placeholder in style_schema)
            for placeholder in ("{env}", "{domain}", "{layer}")
        )

    return max(NAMING_STYLES, key=shared)


@dataclass(frozen=True)
class LogicalName:
    """Always lowercase, because Databricks matches names whatever their case."""

    domain: str
    layer: str
    entity: str

    def __post_init__(self) -> None:
        for part in ("domain", "layer", "entity"):
            object.__setattr__(self, part, getattr(self, part).lower())


def placeholders(name: LogicalName) -> str:
    """The table as generated code refers to it, the same in every Environment."""
    catalog = catalog_setting(name.domain, name.layer)
    schema = schema_setting(name.domain, name.layer)
    return f"${{{catalog}}}.${{{schema}}}.{name.entity}"


def catalog_setting(domain: str, layer: str) -> str:
    """The placeholder for a Domain and Layer's catalog, keyed in lowercase like Logical Names."""
    return f"catalog_{domain}_{layer}".lower()


def schema_setting(domain: str, layer: str) -> str:
    return f"schema_{domain}_{layer}".lower()


def path_placeholder(source: Source) -> str:
    """Where a Source's files land as generated code refers to it, the same in every Environment."""
    return f"${{{_path_setting(source)}}}"


def settings(project: Project, env: str) -> dict[str, str]:
    """The value of every placeholder in one Environment."""
    platform = project.platform
    values = {}
    for domain in platform.domains:
        for layer in (*platform.source_layers, *platform.model_layers):
            catalog, schema = real_names(platform.naming.style, env, domain, layer)
            values[catalog_setting(domain, layer)] = catalog
            values[schema_setting(domain, layer)] = schema
    for source in project.sources:
        # Escaped, because generated code substitutes it between the quotes of a string literal.
        values[_path_setting(source)] = escaped(source.path_in(env))
    return values


def platform_objects(
    platform: Platform, envs: Iterable[str] | None = None
) -> tuple[list[str], list[str]]:
    """Every catalog, and every schema as `catalog.schema`, the project's tables need in `envs`,
    by default every Environment, in Environment, Domain and Layer order."""
    catalogs: dict[str, None] = {}
    schemas: dict[str, None] = {}
    for env in platform.hosts if envs is None else envs:
        for domain in platform.domains:
            for layer in (*platform.source_layers, *platform.model_layers):
                catalog, schema = real_names(platform.naming.style, env, domain, layer)
                catalogs[catalog] = None
                schemas[f"{catalog}.{schema}"] = None
    return list(catalogs), list(schemas)


def logical_name_for(project: Project, real: LogicalName) -> LogicalName | None:
    """The Logical Name behind a real table name in any Environment, if it is one."""
    platform = project.platform
    for env in platform.hosts:
        values = settings(project, env)
        for domain in platform.domains:
            for layer in (*platform.source_layers, *platform.model_layers):
                catalog = values[catalog_setting(domain, layer)].lower()
                schema = values[schema_setting(domain, layer)].lower()
                if (real.domain, real.layer) == (catalog, schema):
                    return LogicalName(domain, layer, real.entity)
    return None


def resolve(generated: str, project: Project, env: str) -> str:
    """Generated code with its placeholders replaced by one Environment's real names.

    `${word}` that names no setting is the author's own text, so it stays as written.
    """
    values = settings(project, env)
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), generated)


def _path_setting(source: Source) -> str:
    # The double underscore keeps `sales` + `eu_orders` apart from `sales_eu` + `orders`.
    return f"path_{source.domain}__{source.name}"
