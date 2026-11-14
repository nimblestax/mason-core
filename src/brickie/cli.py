"""The `brickie` command. Commands stay thin and work on one loaded Project."""

import subprocess
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import wraps
from importlib.metadata import version
from inspect import Parameter, signature
from pathlib import Path
from typing import Annotated, Any, NoReturn

import click
import typer
from pydantic import BaseModel, Field
from typer.core import TyperGroup

from brickie import names, output, scaffold, skills
from brickie.build import compiler
from brickie.check import platform_objects, rules
from brickie.deploy import deploy as delivery
from brickie.deploy import pinned_cli
from brickie.deploy.databricks import DatabricksCli
from brickie.diagnostics import (
    EXIT_CODES,
    USAGE_OR_ENVIRONMENT,
    Diagnostic,
    Failure,
    error,
    errors,
)
from brickie.kinds import KINDS, latest_schema, platform
from brickie.load import config, project

EPILOG = (
    "Exit codes: "
    + ", ".join(f"{code} {meaning.split(':')[0].lower()}" for code, meaning in EXIT_CODES.items())
    + "."
)


class ReportingGroup(TyperGroup):
    """Reports a usage error as an envelope, because it stops a command before its code runs."""

    def invoke(self, ctx: Any) -> Any:
        as_json = "--json" in ctx.args
        try:
            return super().invoke(ctx)
        except typer.TyperException as problem:
            if not as_json:
                raise
            stopped = getattr(problem, "ctx", None)
            label = stopped.info_name if stopped not in (None, ctx) else None
            fix = f"Run `brickie {label} --help`." if label else "Run `brickie --help`."
            found = error("BRK901", "", problem.format_message(), fix)
            _report_failure(label or "usage", True, Failure([found], USAGE_OR_ENVIRONMENT))


# Commands that hand every argument to another program, so they print no envelope.
PASSED_THROUGH = {"databricks"}

app = typer.Typer(cls=ReportingGroup, no_args_is_help=True, add_completion=False, epilog=EPILOG)


def _print_versions(asked: bool) -> None:
    if not asked:
        return
    typer.echo(f"brickie {version('brickie-core')}")
    try:
        typer.echo(f"Databricks CLI {pinned_cli.running_version()}")
    except Failure as failure:
        _report_failure("version", False, failure)
    raise typer.Exit()


@app.callback()
def main(
    show_version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print Brickie's version and the Databricks CLI version it runs.",
            callback=_print_versions,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Bring the software development lifecycle to Databricks pipelines."""


class Ci(StrEnum):
    github = "github"


class Skills(StrEnum):
    all = "all"
    none = "none"


class NamingStyle(StrEnum):
    """Matches `names.NAMING_STYLES`, in the order `brickie init` offers them."""

    domain_catalogs = "domain-catalogs"
    layer_catalogs = "layer-catalogs"
    environment_catalogs = "environment-catalogs"


ProjectOption = Annotated[Path, typer.Option("--project", help="The project folder.")]
JsonOption = Annotated[bool, typer.Option("--json", help="Print one JSON envelope.")]


@dataclass(frozen=True)
class Outcome[Result: BaseModel]:
    """What a command that succeeded tells a person, and tells a machine.

    A command's return annotation names its Result, which the reference documents.
    """

    text: str
    result: Result
    warnings: list[Diagnostic] = field(default_factory=list)


skills_app = typer.Typer(no_args_is_help=True, help="Keep the Brickie Skills in this project.")
app.add_typer(skills_app, name="skills")
# Command groups by name. A command in one is labelled `<group>.<command>`, as in its schema.
GROUPS = {"skills": skills_app}


def every_command() -> dict[str, Any]:
    """Each command by its full name, such as `skills update`, with its group opened up."""
    group: Any = typer.main.get_command(app)
    found = {}
    for name, registered in group.commands.items():
        if name in GROUPS:
            found |= {f"{name} {inner}": cmd for inner, cmd in registered.commands.items()}
        else:
            found[name] = registered
    return found


def callbacks() -> dict[str, Any]:
    """The function behind each command, by its full name."""
    found: dict[str, Any] = {}
    for prefix, typed in [("", app), *((f"{name} ", typed) for name, typed in GROUPS.items())]:
        for info in typed.registered_commands:
            if info.name:  # Only `brickie databricks` has none, and it prints no result.
                found[prefix + info.name] = info.callback
    return found


def command(name: str | None = None, group: str | None = None) -> Callable:
    """Registers a command, which gets `--json` and returns an Outcome or raises a Failure."""

    def register(run: Any) -> Any:
        registered_as = name or run.__name__
        label = f"{group}.{registered_as}" if group else registered_as

        def finish(*args: Any, as_json: bool = False, **kwargs: Any) -> None:
            try:
                outcome = run(*args, **kwargs)
            except Failure as failure:
                _report_failure(label, as_json, failure)
            except Exception as problem:  # Keeps the exit-code contract when Brickie itself breaks.
                traceback.print_exc()
                _report_failure(label, as_json, _unexpected(problem))
            if as_json:
                printed = output.envelope(
                    label, True, outcome.result.model_dump(), outcome.warnings
                )
                typer.echo(printed)
            else:
                for found in outcome.warnings:
                    _print(found)
                typer.echo(outcome.text)

        json_parameter = Parameter(
            "as_json", Parameter.KEYWORD_ONLY, default=False, annotation=JsonOption
        )
        parameters = [*signature(run).parameters.values(), json_parameter]
        # Typer reads the options from this signature, so `--json` needs no line in any command.
        wrapped: Any = wraps(run)(finish)
        wrapped.__signature__ = signature(run).replace(
            parameters=parameters, return_annotation=None
        )
        wrapped.__annotations__ = {**run.__annotations__, "as_json": JsonOption}
        return (GROUPS[group] if group else app).command(registered_as)(wrapped)

    return register


def _report_failure(label: str, as_json: bool, failure: Failure) -> NoReturn:
    if as_json:
        typer.echo(output.envelope(label, False, {}, failure.diagnostics))
    else:
        for diagnostic in failure.diagnostics:
            _print(diagnostic)
    raise typer.Exit(failure.exit_code)


def _unexpected(problem: Exception) -> Failure:
    found = error(
        "BRK905",
        "",
        f"Brickie stopped unexpectedly: {problem}",
        "Read the traceback on stderr. If your machine isn't the cause, report a bug.",
    )
    return Failure([found], USAGE_OR_ENVIRONMENT)


def _require_environment(loaded: project.Project, env: str) -> None:
    known = sorted(loaded.platform.hosts)
    if env not in known:
        found = error(
            "BRK902",
            platform.FILE_NAME,
            f"`{env}` isn't an Environment in this project.",
            f"Use one of: {', '.join(known)}.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)


def _print(diagnostic: Diagnostic) -> None:
    where = f" {diagnostic.file}" if diagnostic.file else ""
    marker = " (warning)" if diagnostic.severity == "warning" else ""
    typer.echo(f"{diagnostic.rule}{where}{marker}: {diagnostic.message}")
    typer.echo(f"  Fix: {diagnostic.fix}")


ONE_WORKSPACE_OR_MANY = (
    "Every Naming Style works with one workspace for all Environments,"
    " or one workspace per Environment."
)


class Created(BaseModel):
    project: str = Field(description="The folder the project was created in.")
    naming_style: str = Field(description="The Naming Style written into its Platform Contract.")
    catalogs: list[str] = Field(description="The catalogs to create before deploying.")
    schemas: list[str] = Field(
        description="The schemas to create before deploying, as `catalog.schema`."
    )
    skills: list[str] = Field(description="The Brickie Skill folders written.")
    skills_left_alone: list[str] = Field(
        description="The Brickie Skill folders that already existed, which were left as they were."
    )
    volumes: list[str] = Field(
        description="The Volumes the Sources read in dev, as `catalog.schema.volume`, to create"
        " before deploying."
    )
    example: str | None = Field(description="The example written, or `null` for a new project.")
    uploads: list[str] = Field(
        description="With `--example`, the commands that upload day 1's data to each Source's"
        " path in dev."
    )


@command()
def init(
    ci: Annotated[Ci, typer.Option("--ci", help="CI provider to write files for.")] = Ci.github,
    host: Annotated[str, typer.Option("--host", help="Workspace URL.")] = scaffold.PLACEHOLDER_HOST,
    naming_style: Annotated[
        NamingStyle | None,
        typer.Option(
            "--naming-style",
            help="Where tables live. Asked at a terminal when left out; otherwise domain-catalogs.",
        ),
    ] = None,
    with_skills: Annotated[
        Skills,
        typer.Option(
            "--skills",
            help="Brickie Skills to write for coding agents, into `.agents/skills/` and"
            " `.claude/skills/`.",
        ),
    ] = Skills.all,
    example: Annotated[
        str | None,
        typer.Option(
            "--example",
            help="Write an example project with its sample data, such as `kettle`, instead of"
            " a new one. It keeps the Naming Style it ships with.",
            show_default=False,
        ),
    ] = None,
    folder: Annotated[
        Path,
        typer.Argument(
            help="The folder to create the project in, made if missing. Its name is the"
            " project's name, except for an example, which keeps its own.",
            show_default=False,
        ),
    ] = Path("."),
) -> Outcome[Created]:
    """Create a working project in a folder, by default the current one."""
    if example:
        scaffold.refuse_unknown_example(example)
        if naming_style:
            raise Failure([_EXAMPLE_WITH_NAMING_STYLE], USAGE_OR_ENVIRONMENT)
    scaffold.refuse_existing_project(folder)  # Before the question, so no answer is wasted.
    if example:
        scaffold.write_example(folder, example, host, ci.value)
    else:
        style = naming_style or (
            _ask_naming_style() if _at_a_terminal() else NamingStyle.domain_catalogs
        )
        scaffold.write_project(folder, host, ci.value, style.value)
    installed = skills.install(folder) if with_skills == Skills.all else skills.Installed([], [])
    loaded = project.load(folder)
    catalogs, schemas = names.platform_objects(loaded.platform)
    created = Created(
        project=str(folder),
        naming_style=loaded.platform.naming.style,
        catalogs=catalogs,
        schemas=schemas,
        skills=installed.written,
        skills_left_alone=installed.left_alone,
        volumes=_volumes(loaded),
        example=example,
        uploads=_uploads(loaded, folder) if example else [],
    )
    return Outcome(_created_text(created), created, skills.ignored(folder))


# An example ships with its Naming Style, so the docs can show its files as they are.
_EXAMPLE_WITH_NAMING_STYLE = error(
    "BRK901",
    "",
    "`brickie init --example` writes the example with the Naming Style it ships with, so it takes"
    " no `--naming-style`.",
    "Remove `--naming-style`, or leave out `--example` to start a new project in that style.",
)


DEV = "dev"
FIRST_DAY = Path("data/day-1")


def _volumes(loaded: project.Project) -> list[str]:
    """Each Volume a Source's files land in, in dev."""
    found: dict[str, None] = {}
    for source in loaded.sources:
        parts = source.path_in(DEV).split("/")
        if len(parts) > 4 and parts[1] == "Volumes":
            found[".".join(parts[2:5])] = None
    return list(found)


def _uploads(loaded: project.Project, folder: Path) -> list[str]:
    """For each Source with sample data, the command that lands day 1 at its path in dev."""
    return [
        f"brickie databricks fs cp --recursive {(FIRST_DAY / source.name).as_posix()}"
        f" dbfs:{source.path_in(DEV)}"
        for source in loaded.sources
        if (folder / FIRST_DAY / source.name).is_dir()
    ]


def _at_a_terminal() -> bool:
    return sys.stdin.isatty()


def _ask_naming_style() -> NamingStyle:
    """Asked on stderr, so `--json` output on stdout stays one envelope."""
    typer.echo("Where should tables live? A silver orders table in prod would be:", err=True)
    for style in names.NAMING_STYLES:
        typer.echo(f"  {style:<22}{names.example_table(style)}", err=True)
    typer.echo(ONE_WORKSPACE_OR_MANY, err=True)
    chosen = typer.prompt(
        "Naming Style",
        default=NamingStyle.domain_catalogs.value,
        type=click.Choice([style.value for style in NamingStyle]),
        err=True,
    )
    return NamingStyle(chosen)


def _created_text(created: Created) -> str:
    lines = [
        f"Created a Brickie project in {created.project}, with the {created.naming_style}"
        " Naming Style.",
        ONE_WORKSPACE_OR_MANY,
        "",
        "Create these in Unity Catalog before you deploy:",
        "  Catalogs:",
        *(f"    {catalog}" for catalog in created.catalogs),
        "  Schemas:",
        *(f"    {schema}" for schema in created.schemas),
    ]
    if created.volumes:
        lines += ["  Volumes:", *(f"    {volume}" for volume in created.volumes)]
    if created.uploads:
        lines += [
            "",
            f"Then upload day 1's data from {created.project}:",
            *(f"  {upload}" for upload in created.uploads),
            "After the first deploy, upload data/day-2 the same way to see changes arrive.",
        ]
    if created.skills:
        lines += [
            "",
            "Wrote Brickie Skills for coding agents:",
            *(f"  {s}" for s in created.skills),
        ]
    if created.skills_left_alone:
        lines += [
            "",
            "Left these skill folders as they were:",
            *(f"  {s}" for s in created.skills_left_alone),
        ]
    return "\n".join(lines)


class Valid(BaseModel):
    """Empty: `validate` reports what it finds as diagnostics."""


@command()
def validate(
    check_platform: Annotated[
        bool,
        typer.Option(
            "--platform",
            help="Also check, in the Environment's workspace, that the catalogs and schemas"
            " the project needs exist.",
        ),
    ] = False,
    env: Annotated[
        str | None,
        typer.Option(
            "--env",
            help="The Environment whose workspace `--platform` checks. Defaults to the default"
            " Environment.",
            show_default=False,
        ),
    ] = None,
    root: ProjectOption = Path("."),
) -> Outcome[Valid]:
    """Check config and SQL references. With `--platform`, also check the workspace."""
    if env and not check_platform:
        raise Failure([_ENV_WITHOUT_PLATFORM], USAGE_OR_ENVIRONMENT)
    loaded = project.load(root)
    problems = rules.check(loaded)
    if check_platform:
        # One Environment, because each CI stage signs in as that Environment's identity alone.
        checked = env or loaded.platform.default_environment
        _require_environment(loaded, checked)
        problems += platform_objects.check(loaded, checked, DatabricksCli())
    problems += skills.drift(root)
    if errors(problems):
        raise Failure(problems)
    return Outcome("Valid.", Valid(), warnings=problems)


# Plain `validate` is the same in every Environment, so `--env` alone would change nothing.
_ENV_WITHOUT_PLATFORM = error(
    "BRK901",
    "",
    "`brickie validate --env` names the Environment `--platform` checks, and `--platform` is"
    " missing. Without it, `brickie validate` reads no workspace.",
    "Add `--platform`, such as `brickie validate --platform --env dev`, or remove `--env`.",
)


class SkillsUpdated(BaseModel):
    skills: list[str] = Field(
        description="The Brickie Skill folders written. A skill already up to date isn't listed."
    )


@command("update", group="skills")
def skills_update(
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace skills edited since Brickie wrote them."),
    ] = False,
    root: ProjectOption = Path("."),
) -> Outcome[SkillsUpdated]:
    """Refresh both copies of each Brickie Skill to this Brickie's version."""
    scaffold.require_project(root)
    written = skills.update(root, force)
    updated = SkillsUpdated(skills=written)
    if not written:
        return Outcome("Every Brickie Skill is up to date.", updated)
    lines = ["Updated these Brickie Skills. Commit them:", *(f"  {skill}" for skill in written)]
    return Outcome("\n".join(lines), updated)


class KindSchema(BaseModel):
    kind: str = Field(description="The Kind described.")
    version: int = Field(description="The newest version of the Kind this Brickie supports.")
    json_schema: dict[str, Any] = Field(description="The Kind's JSON Schema at that version.")


@command()
def schema(
    kind: Annotated[str, typer.Argument(help="The Kind to describe.")],
) -> Outcome[KindSchema]:
    """Print a Kind's fields from the installed Brickie. Needs no project."""
    if kind not in KINDS:
        raise Failure([config.unknown_kind(kind, "")], USAGE_OR_ENVIRONMENT)
    version, json_schema = latest_schema(kind)
    result = KindSchema(kind=kind, version=version, json_schema=json_schema)
    return Outcome(output.fields(kind, version, json_schema), result)


class Package(BaseModel):
    """Without `--env`, `compile` writes the generated code."""

    package: str = Field(description="The folder the generated code was written to.")


class Sql(BaseModel):
    """With `--env`, `compile` prints it instead."""

    env: str = Field(description="The Environment the SQL is for.")
    sql: str = Field(description="Every generated file as runnable SQL for that Environment.")


@command("compile")
def compile_(
    env: Annotated[
        str | None, typer.Option("--env", help="Print runnable SQL for this Environment.")
    ] = None,
    root: ProjectOption = Path("."),
) -> Outcome[Package | Sql]:
    """Write generated code, or print it for one Environment."""
    loaded = project.load(root)
    if env:
        _require_environment(loaded, env)
        sql = compiler.print_for(loaded, env)
        return Outcome(sql, Sql(env=env, sql=sql))
    package = compiler.write_package(loaded)
    return Outcome(f"Wrote {package}", Package(package=str(package)))


class Deployed(BaseModel):
    env: str = Field(description="The Environment deployed and refreshed.")


@command()
def deploy(
    env: Annotated[
        str | None,
        typer.Option(
            "--env",
            help="The Environment to deploy. Required: a deploy never uses the default"
            " Environment.",
            show_default=False,
        ),
    ] = None,
    root: ProjectOption = Path("."),
) -> Outcome[Deployed]:
    """Deploy to an Environment and refresh its tables."""
    if env is None:
        raise Failure([_DEPLOY_WITHOUT_ENV], USAGE_OR_ENVIRONMENT)
    loaded = project.load(root)
    _require_environment(loaded, env)
    delivery.deploy(loaded, env, DatabricksCli())
    return Outcome(f"Deployed to {env}", Deployed(env=env))


# `--env` is optional on the command line only so this fix, not a usage message, reaches the user.
_DEPLOY_WITHOUT_ENV = error(
    "BRK901",
    "",
    "`brickie deploy` needs `--env`, so every deploy says where it goes. It never uses the"
    " default Environment.",
    "Add the Environment to deploy, such as `brickie deploy --env dev`.",
)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    add_help_option=False,
)
def databricks(context: typer.Context) -> None:
    """Run the Databricks CLI Brickie runs, with your arguments passed through."""
    try:
        executable = pinned_cli.databricks()
    except Failure as failure:
        _report_failure("databricks", False, failure)
    ran = subprocess.run([executable, *context.args])
    raise typer.Exit(ran.returncode)
