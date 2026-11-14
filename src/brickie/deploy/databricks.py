"""The Databricks boundary: every workspace call goes through here."""

import json
import os
import subprocess
import sys
from collections import deque
from datetime import UTC, datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any, Protocol

from brickie.deploy import pinned_cli
from brickie.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error

# How many of the CLI's last lines a failure keeps, since the CLI's own output goes to stderr.
KEPT_LINES = 10

# The workspace's clock and this machine's can differ a little, so errors are read from a bit
# before the refresh started. A failed deploy takes longer than this, so no older error shows up.
CLOCK_SKEW = timedelta(minutes=1)


class WorkspaceError(Failure):
    def __init__(self, message: str, rule: str = "BRK904", fix: str = "Read the log on stderr."):
        super().__init__([error(rule, "", message, fix)], USAGE_OR_ENVIRONMENT)


class Workspace(Protocol):
    def deploy_bundle(self, package: Path, target: str) -> None: ...

    def run_job(self, package: Path, target: str, job: str) -> None: ...

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        """The errors of each pipeline's newest update that failed since `since`."""
        ...


class DatabricksCli:
    """Runs Brickie's pinned Databricks CLI, found or downloaded at the first call."""

    @cached_property
    def _executable(self) -> str:
        return str(pinned_cli.databricks())

    def deploy_bundle(self, package: Path, target: str) -> None:
        self._stream(package, "bundle", "deploy", "--target", target)

    def run_job(self, package: Path, target: str, job: str) -> None:
        self._stream(package, "bundle", "run", "--target", target, job)

    def pipeline_errors(self, package: Path, target: str, since: datetime) -> list[str]:
        summary = self._json(package, "bundle", "summary", "--target", target, "-o", "json")
        pipelines = summary.get("resources", {}).get("pipelines", {}).values()
        start = (since - CLOCK_SKEW).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        errors = []
        for pipeline in pipelines:
            if "id" not in pipeline:
                continue  # Never deployed, so it has no log.
            events = self._json(
                package,
                *("pipelines", "list-pipeline-events", pipeline["id"], "--target", target),
                *("-o", "json", "--filter", f"level='ERROR' AND timestamp >= '{start}'"),
            )
            errors.extend(failed_update_errors(events))
        return errors

    def catalogs(self, host: str) -> set[str]:
        listed = self._json(None, "catalogs", "list", "--output", "json", host=host)
        return {catalog["name"] for catalog in listed}

    def schemas(self, host: str, catalog: str) -> set[str]:
        listed = self._json(None, "schemas", "list", catalog, "--output", "json", host=host)
        return {schema["name"] for schema in listed}

    def _stream(self, package: Path, *arguments: str) -> None:
        command = [self._executable, *arguments]
        last_lines: deque[str] = deque(maxlen=KEPT_LINES)
        # Its output goes to stderr, so stdout only ever holds what Brickie prints.
        with _start(command, package, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as cli:
            for line in cli.stdout or []:
                sys.stderr.write(line)
                last_lines.append(line.rstrip())
        if cli.returncode:
            shown = "\n".join(last_lines)
            raise WorkspaceError(
                f"databricks {' '.join(arguments)} failed. Its last lines:\n{shown}"
            )

    def _json(self, package: Path | None, *arguments: str, host: str | None = None) -> Any:
        """Run from a bundle `package`, which names each target's workspace, or with no package
        against `host`, whatever workspace the shell points at."""
        command = [self._executable, *arguments]
        env = {**os.environ, "DATABRICKS_HOST": host} if host else None
        # Its log goes to the stderr this process was started with, so stdout stays Brickie's.
        with _start(command, package, env=env, stdout=subprocess.PIPE, stderr=None) as cli:
            printed = cli.stdout.read() if cli.stdout else ""
        if cli.returncode:
            raise WorkspaceError(f"databricks {' '.join(arguments)} failed.")
        try:
            return json.loads(printed)
        except json.JSONDecodeError as failure:
            raise WorkspaceError(
                f"databricks {' '.join(arguments)} didn't print JSON."
            ) from failure


def _start(command: list[str], package: Path | None, **streams: Any) -> subprocess.Popen[str]:
    try:
        return subprocess.Popen(command, cwd=package, text=True, **streams)
    except FileNotFoundError as failure:
        raise WorkspaceError(
            f"Brickie can't run the Databricks CLI at {command[0]}: {failure.strerror}.",
            "BRK903",
            f"Point {pinned_cli.OVERRIDE} at a Databricks CLI, or unset it so Brickie downloads"
            " its own.",
        ) from failure


def failed_update_errors(events: list[dict]) -> list[str]:
    """The first line of each error in the newest update, from a pipeline's ERROR events.

    Events come newest first. A failed flow logs its own error and then the update logs a summary,
    so the flows' errors are kept, and the update's own only when no flow failed.
    """
    if not events:
        return []
    newest = _origin(events[0]).get("update_id")
    in_update = [found for found in reversed(events) if _origin(found).get("update_id") == newest]
    from_flows = [found for found in in_update if _origin(found).get("flow_name")]
    errors = []
    for found in from_flows or in_update:
        message = _error_message(found)
        if message and message not in errors:
            errors.append(message)
    return errors


def _origin(found: dict) -> dict:
    return found.get("origin", {})


def _error_message(found: dict) -> str:
    exceptions = found.get("error", {}).get("exceptions") or [{}]
    message = exceptions[0].get("message") or found.get("message") or ""
    return message.splitlines()[0] if message else ""
