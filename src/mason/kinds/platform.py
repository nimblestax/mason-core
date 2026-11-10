"""The Platform Contract: `mason.platform.yaml`."""

from collections.abc import Callable
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

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


class Layers(BaseModel):
    """The Layers, in the order data flows through them."""

    model_config = STRICT

    sources: list[str] = Field(
        min_length=2, max_length=2, description="Exactly two source Layers, bronze then silver."
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
    """The shared facts about a project's platform."""

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
                "{defaults} each set `default: true`, and only one Environment can be the"
                " default.",
                {
                    "defaults": " and ".join(defaults),
                    "fix": "Keep `default: true` on one Environment and remove it from the"
                    " others.",
                },
            )
        return environments

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
        bronze, silver = self.naming.layers.sources
        return bronze, silver

    @property
    def model_layers(self) -> tuple[str, ...]:
        return tuple(self.naming.layers.models)


VERSIONS: dict[int, type[BaseModel]] = {1: PlatformV1}
Platform = PlatformV1

# `UPGRADES[n]` turns version n into version n + 1. A new version adds its model to `VERSIONS`,
# points `Platform` at it, and adds one step here.
UPGRADES: dict[int, Callable[[Any], BaseModel]] = {}
