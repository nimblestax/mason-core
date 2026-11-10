"""The Platform Contract: `mason.platform.yaml`."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from mason import names
from mason.kinds.base import STRICT, ExactInteger, Identifier, unique

FILE_NAME = "mason.platform.yaml"
KIND = "platform"

PLACEHOLDERS = ("{env}", "{domain}", "{layer}")

# The reserved Domain that holds what every Domain reads, such as conformed dimensions.
SHARED_DOMAIN = "shared"


class Environment(BaseModel):
    """One Environment's settings."""

    model_config = STRICT

    host: str | None = Field(
        default=None,
        description="Workspace URL. Required on dev; test and prod use dev's unless they set"
        " their own.",
    )
    default: bool = Field(
        default=False,
        description="Whether commands that read use this Environment when `--env` is left out."
        " At most one Environment sets it; with none, dev is the default. `mason deploy` always"
        " needs `--env`.",
    )


def _checked(environments: dict[str, Environment]) -> dict[str, Environment]:
    """dev has a host, and at most one Environment is the default."""
    dev = environments.get("dev")
    if dev is None or dev.host is None:
        # A rule ID as the error type reaches the user as that rule, with this fix.
        raise PydanticCustomError(
            "MSN122",
            "dev has no `host`, and test and prod use dev's unless they set their own.",
            {"fix": "Add `host` under `environments.dev`, set to dev's workspace URL."},
        )
    defaults = [env for env, settings in environments.items() if settings.default]
    if len(defaults) > 1:
        raise PydanticCustomError(
            "MSN123",
            "{defaults} each set `default: true`, and only one Environment can be the" " default.",
            {
                "defaults": " and ".join(defaults),
                "fix": "Keep `default: true` on one Environment and remove it from the" " others.",
            },
        )
    return environments


class Layers(BaseModel):
    """The Layers, in the order data flows through them."""

    model_config = STRICT

    # Any list is read, so the upgrade to version 2 can say that source Layers are fixed.
    sources: list[str] = Field(
        default=["bronze", "silver"],
        description="Always `[bronze, silver]`, and optional. Version 2 has no such field.",
    )
    models: list[str] = Field(
        min_length=1, description="One or more model Layers, read left to right."
    )


class Naming(BaseModel):
    """How Logical Names map to real catalogs and schemas."""

    model_config = STRICT

    # Aliases, because `schema` is taken on every Pydantic model.
    catalog_pattern: str = Field(
        alias="catalog",
        description="The catalog pattern, built from `{env}`, `{domain}` and `{layer}`.",
    )
    schema_pattern: str = Field(
        alias="schema",
        description="The schema pattern, built from `{env}`, `{domain}` and `{layer}`.",
    )
    layers: Layers = Field(description="The source and model Layers.")

    @field_validator("catalog_pattern", "schema_pattern")
    @classmethod
    def _only_known_placeholders(cls, pattern: str) -> str:
        rest = pattern
        for placeholder in PLACEHOLDERS:
            rest = rest.replace(placeholder, "")
        if "{" in rest or "}" in rest:
            # The values go in as context, because the message template reads its own braces.
            raise PydanticCustomError(
                "unknown_placeholder",
                "`{pattern}` may hold only {allowed} in braces.",
                {"pattern": pattern, "allowed": "{env}, {domain} and {layer}"},
            )
        return pattern


class PlatformV1(BaseModel):
    """The shared facts about a project's platform, as Mason 0.3.0 and before wrote them.

    Read only to upgrade to version 2.
    """

    model_config = ConfigDict(**STRICT, title="Mason Platform Contract")

    kind: Literal["platform"] = Field(description="The Kind of this file.")
    version: Annotated[Literal[1], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    name: str = Field(min_length=1, description="The project's name.")
    environments: dict[str, Environment] = Field(
        min_length=1, description="Settings per Environment."
    )
    naming: Naming = Field(description="The catalog and schema patterns, and the Layers.")
    domains: list[Identifier] = Field(
        json_schema_extra={"uniqueItems": True},
        description="The Domains, one folder each under `domains/`.",
    )

    @field_validator("environments")
    @classmethod
    def _dev_has_a_host(cls, environments: dict[str, Environment]) -> dict[str, Environment]:
        return _checked(environments)

    @field_validator("domains")
    @classmethod
    def _domains_are_unique(cls, domains: list[str]) -> list[str]:
        return unique(domains, "Domain")


# The source Layers are fixed: every Source makes one table in each.
SOURCE_LAYERS = ("bronze", "silver")

# The values of `names.NAMING_STYLES`, which holds each style's patterns.
NamingStyle = Literal["domain-catalogs", "layer-catalogs", "environment-catalogs"]


def _style_choices(json_schema: dict[str, Any]) -> None:
    """Each style as its own choice with a description, so editors explain it as they complete."""
    json_schema.pop("enum", None)
    json_schema.pop("type", None)
    json_schema["oneOf"] = [
        {
            "const": style,
            "description": f"`sales.silver.orders` is `{names.example_table(style)}` in prod.",
        }
        for style in names.NAMING_STYLES
    ]


class ModelLayers(BaseModel):
    """The model Layers. The source Layers are always bronze and silver."""

    model_config = STRICT

    models: list[Identifier] = Field(
        min_length=1,
        description="One or more model Layers, in any order. Each is a folder under `models/`.",
    )

    @field_validator("models")
    @classmethod
    def _models_are_not_source_layers(cls, models: list[str]) -> list[str]:
        # Catalog and schema names ignore case, so `Silver` would be silver's schema.
        taken = [layer for layer in models if layer.lower() in SOURCE_LAYERS]
        if taken:
            raise PydanticCustomError(
                "MSN126",
                "`naming.layers.models` names {taken}, which is a source Layer. Sources fill"
                " bronze and silver, and Gold Models fill only model Layers.",
                {
                    "taken": " and ".join(taken),
                    "fix": "Rename the model Layer, such as to `gold` or `marts`, and rename its"
                    " folder under `models/` to match.",
                },
            )
        return unique(models, "model Layer")


class NamingV2(BaseModel):
    """How Logical Names map to real catalogs and schemas."""

    model_config = STRICT

    style: NamingStyle = Field(
        description="Where tables live. In prod, `sales.silver.orders` is "
        + ", ".join(
            f"`{names.example_table(style)}` under `{style}`" for style in names.NAMING_STYLES
        )
        + ".",
        json_schema_extra=_style_choices,
    )
    layers: ModelLayers = Field(description="The model Layers.")

    @model_validator(mode="before")
    @classmethod
    def _no_patterns(cls, naming: Any) -> Any:
        if isinstance(naming, dict) and ("catalog" in naming or "schema" in naming):
            raise PydanticCustomError(
                "MSN124",
                "`naming` sets `catalog` and `schema` patterns, and version 2 takes only a"
                " Naming Style.",
                {
                    "fix": "Replace `catalog` and `schema` with `style`, set to"
                    f" {_style_list()}. Custom patterns aren't supported yet."
                },
            )
        return naming


def _style_list() -> str:
    *first, last = (f"`{style}`" for style in names.NAMING_STYLES)
    return f"{', '.join(first)} or {last}"


class PlatformV2(BaseModel):
    """The shared facts about a project's platform."""

    model_config = ConfigDict(**STRICT, title="Mason Platform Contract")

    kind: Literal["platform"] = Field(description="The Kind of this file.")
    version: Annotated[Literal[2], ExactInteger] = Field(
        description="The schema version of this Kind."
    )
    name: str = Field(min_length=1, description="The project's name.")
    environments: dict[str, Environment] = Field(
        min_length=1, description="Settings per Environment."
    )
    naming: NamingV2 = Field(description="The Naming Style, and the model Layers.")
    domains: list[Identifier] = Field(
        json_schema_extra={"uniqueItems": True},
        description="The Domains, one folder each under `domains/`.",
    )

    @field_validator("environments")
    @classmethod
    def _dev_has_a_host(cls, environments: dict[str, Environment]) -> dict[str, Environment]:
        return _checked(environments)

    @field_validator("domains")
    @classmethod
    def _domains_are_unique(cls, domains: list[str]) -> list[str]:
        return unique(domains, "Domain")

    @property
    def hosts(self) -> dict[str, str]:
        """Each Environment's workspace URL. One with no `host` uses dev's."""
        dev = self.environments["dev"].host or ""  # Never empty: `_dev_has_a_host` checks it.
        return {env: settings.host or dev for env, settings in self.environments.items()}

    @property
    def default_environment(self) -> str:
        """What commands that read use when `--env` is left out."""
        marked = [env for env, settings in self.environments.items() if settings.default]
        return marked[0] if marked else "dev"

    @property
    def source_layers(self) -> tuple[str, str]:
        return SOURCE_LAYERS

    @property
    def model_layers(self) -> tuple[str, ...]:
        return tuple(self.naming.layers.models)


def upgrade_to_v2(old: PlatformV1) -> PlatformV2:
    """Patterns that match a Naming Style become that style. Anything else can't be kept."""
    if tuple(old.naming.layers.sources) != SOURCE_LAYERS:
        raise PydanticCustomError(
            "MSN125",
            "`naming.layers.sources` is {sources}, and the source Layers are always bronze"
            " and silver.",
            {
                "sources": f"`[{', '.join(old.naming.layers.sources)}]`",
                "fix": "Remove `naming.layers.sources`. To add a Layer, add it to"
                " `naming.layers.models`.",
            },
        )
    catalog, schema = old.naming.catalog_pattern, old.naming.schema_pattern
    style = names.style_for(catalog, schema)
    if style is None:
        closest = names.closest_style(catalog, schema)
        raise PydanticCustomError(
            "MSN124",
            "`naming` sets the patterns {patterns}, which aren't a Naming Style. The closest"
            " is {closest}. Custom patterns aren't supported yet.",
            {
                "patterns": f"`{catalog}` / `{schema}`",
                "closest": f"`{closest}`",
                "fix": f"Set `version: 2`, and replace `catalog` and `schema` with `style:"
                f" {closest}` or another Naming Style. If the project is deployed, check where"
                " the style puts its tables first: a new style moves them.",
            },
        )
    return PlatformV2.model_validate(
        {
            **old.model_dump(include={"kind", "name", "environments", "domains"}),
            "version": 2,
            "naming": {"style": style, "layers": {"models": old.naming.layers.models}},
        }
    )


VERSIONS: dict[int, type[BaseModel]] = {1: PlatformV1, 2: PlatformV2}
Platform = PlatformV2

# `UPGRADES[n]` turns version n into version n + 1. A new version adds its model to `VERSIONS`,
# points `Platform` at it, and adds one step here. A step that can't upgrade a file raises a
# `PydanticCustomError` whose type is the Rule it breaks, with the fix in its context.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {1: upgrade_to_v2}
