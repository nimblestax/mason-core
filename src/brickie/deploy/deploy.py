"""`brickie deploy`: ships one Environment and refreshes it."""

from datetime import datetime

from brickie.build import bundle, compiler
from brickie.check import rules
from brickie.deploy.databricks import Workspace, WorkspaceError
from brickie.diagnostics import (
    DOCS_ROOT,
    USAGE_OR_ENVIRONMENT,
    Diagnostic,
    Failure,
    error,
    errors,
)
from brickie.load.project import Project

RECOVERY_GUIDE = f"{DOCS_ROOT}/guides/recover-from-a-failed-refresh.md"


class InvalidProject(Failure):
    pass


def deploy(project: Project, env: str, workspace: Workspace) -> None:
    problems = errors(rules.check(project))
    if problems:
        raise InvalidProject(problems)
    package = compiler.write_package(project)
    workspace.deploy_bundle(package, env)
    started = datetime.now().astimezone()
    try:
        workspace.run_job(package, env, bundle.REFRESH_JOB)
    except WorkspaceError as failure:
        try:
            messages = workspace.pipeline_errors(package, env, started)
        except WorkspaceError as lookup:
            raise _unexplained(failure, lookup) from failure
        if not messages:
            raise failure
        found = [refresh_failure(message) for message in messages]
        raise Failure(found, USAGE_OR_ENVIRONMENT) from failure


def _unexplained(failure: WorkspaceError, lookup: WorkspaceError) -> WorkspaceError:
    """The refresh's own failure, saying Brickie tried to read why and couldn't."""
    [ran] = failure.diagnostics
    [read] = lookup.diagnostics
    return WorkspaceError(
        f"{ran.message}\nBrickie couldn't read the pipelines' errors to say why: {read.message}"
    )


def refresh_failure(message: str) -> Diagnostic:
    """A pipeline's error during the refresh, with how to recover from it."""
    if "UNRESOLVED_COLUMN" in message:
        fix = (
            "Correct the column's name. If an Expectation names a column bronze doesn't have"
            " yet, deploy without the rule so bronze picks up the column, then add the rule back."
            f" See {RECOVERY_GUIDE}."
        )
        return error("BRK906", "", message, fix)
    if "EXPECTATION_VIOLATION" in message:
        fix = (
            "The row that broke the rule stays in bronze, so every refresh fails on it again."
            " Correct the rule, or change its `action` to `quarantine` or `warn`, then deploy."
            f" See {RECOVERY_GUIDE}."
        )
        return error("BRK907", "", message, fix)
    fix = "Fix the cause, then deploy again. The pipeline's event log in the workspace has more."
    return error("BRK908", "", message, fix)
