"""Mason runs its own pinned Databricks CLI, downloaded once and checked against its checksum."""

import hashlib
import io
import json
import os
import re
import threading
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mason import cli
from mason.deploy import databricks_cli_release, pinned_cli

runner = CliRunner()

PINNED = "9.9.9"


def fake_cli(calls: Path) -> str:
    """A Databricks CLI that records each call and succeeds."""
    return f'#!/bin/sh\necho "$@" >> {calls}\necho "Databricks CLI v{PINNED}"\n'


def archive(binary: str, script: str) -> bytes:
    """A release archive, laid out as Databricks publishes it."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as written:
        written.writestr("LICENSE", "Databricks' own licence.\n")
        written.writestr(binary, script)
    return buffer.getvalue()


@dataclass
class Releases:
    """A fake of Databricks' GitHub releases, serving one archive."""

    url: str
    archive: bytes = b""
    delay_seconds: float = 0
    status: int = 200
    requests: list[str] = field(default_factory=list)


@pytest.fixture
def releases() -> Iterator[Releases]:
    served = Releases("")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            served.requests.append(self.path)
            time.sleep(served.delay_seconds)
            self.send_response(served.status)
            self.send_header("Content-Length", str(len(served.archive)))
            self.end_headers()
            self.wfile.write(served.archive)

        def log_message(self, format: str, *args: object) -> None:
            pass  # Keeps test output clean.

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    served.url = f"http://127.0.0.1:{server.server_port}"
    yield served
    server.shutdown()


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch, releases: Releases, tmp_path: Path) -> Iterator[Path]:
    """Points Mason at the fake releases, with this archive's checksum pinned for this machine."""
    calls = tmp_path / "calls"
    releases.archive = archive(pinned_cli.binary_name(), fake_cli(calls))
    checksum = hashlib.sha256(releases.archive).hexdigest()
    monkeypatch.setattr(pinned_cli, "RELEASES", releases.url)
    monkeypatch.setattr(pinned_cli, "VERSION", PINNED)
    monkeypatch.setattr(pinned_cli, "CHECKSUMS", {pinned_cli.platform_name(): checksum})
    monkeypatch.setattr(pinned_cli, "cache_folder", lambda: tmp_path / "cache")
    monkeypatch.delenv(pinned_cli.OVERRIDE, raising=False)
    yield calls


@pytest.fixture
def project(tmp_path: Path) -> Path:
    folder = tmp_path / "shop"
    assert runner.invoke(cli.app, ["init", str(folder)]).exit_code == 0
    return folder


def deploy(project: Path):
    return runner.invoke(cli.app, ["deploy", "--env", "dev", "--json", "--project", str(project)])


def test_the_first_deploy_downloads_the_pinned_cli_and_the_next_reuses_it(
    pinned: Path, releases: Releases, project: Path
):
    first = deploy(project)
    second = deploy(project)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert releases.requests == [
        f"/v{PINNED}/databricks_cli_{PINNED}_{pinned_cli.platform_name()}.zip"
    ]
    assert pinned.read_text().splitlines().count("bundle deploy --target dev") == 2


def test_an_archive_whose_checksum_does_not_match_is_refused_and_nothing_runs(
    pinned: Path, releases: Releases, project: Path
):
    releases.archive = archive(pinned_cli.binary_name(), "#!/bin/sh\necho tampered\n")

    result = deploy(project)

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN910"
    assert not pinned.exists()
    assert not list((pinned.parent / "cache").rglob(pinned_cli.binary_name()))


def test_each_cli_version_has_its_own_place_in_the_cache(
    pinned: Path, releases: Releases, monkeypatch: pytest.MonkeyPatch
):
    older = pinned_cli.databricks()
    newer_archive = archive(pinned_cli.binary_name(), "#!/bin/sh\necho 'Databricks CLI v10.0.0'\n")
    releases.archive = newer_archive
    monkeypatch.setattr(pinned_cli, "VERSION", "10.0.0")
    monkeypatch.setattr(
        pinned_cli,
        "CHECKSUMS",
        {pinned_cli.platform_name(): hashlib.sha256(newer_archive).hexdigest()},
    )

    newer = pinned_cli.databricks()

    assert older != newer
    assert older.read_text() == fake_cli(pinned)
    assert "v10.0.0" in newer.read_text()
    assert len(releases.requests) == 2


def test_two_runs_at_once_download_the_cli_once(pinned: Path, releases: Releases):
    releases.delay_seconds = 0.5
    found: list[Path] = []
    runs = [threading.Thread(target=lambda: found.append(pinned_cli.databricks())) for _ in "ab"]

    for run in runs:
        run.start()
    for run in runs:
        run.join()

    assert len(releases.requests) == 1
    assert found[0] == found[1]


def own_cli(folder: Path, version: str) -> Path:
    """A Databricks CLI someone installed themselves, which records its calls beside it."""
    script = folder / "own-databricks"
    script.write_text(
        f'#!/bin/sh\necho "$@" >> {folder}/own-calls\necho "Databricks CLI v{version}"\n'
    )
    script.chmod(0o755)
    return script


def test_a_cli_named_by_mason_databricks_cli_at_the_minimum_is_used_with_no_download(
    pinned: Path, releases: Releases, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(own_cli(tmp_path, pinned_cli.MINIMUM)))

    result = deploy(project)

    assert result.exit_code == 0, result.output
    assert releases.requests == []
    assert "bundle deploy --target dev" in (tmp_path / "own-calls").read_text()


def test_a_cli_named_by_mason_databricks_cli_below_the_minimum_fails_and_nothing_runs(
    pinned: Path, releases: Releases, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(own_cli(tmp_path, "0.200.0")))

    result = deploy(project)

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN911"
    assert "0.200.0" in diagnostic["message"]
    assert pinned_cli.MINIMUM in diagnostic["message"]
    assert (tmp_path / "own-calls").read_text().splitlines() == ["--version"]
    assert releases.requests == []


def test_a_cli_named_by_mason_databricks_cli_that_does_not_exist_fails(
    pinned: Path, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(tmp_path / "nowhere" / "databricks"))

    result = deploy(project)

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN903"


def test_a_download_that_fails_says_so_with_a_rule_id(
    pinned: Path, releases: Releases, project: Path
):
    releases.status = 404

    result = deploy(project)

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN912"
    assert "404" in diagnostic["message"]
    assert not pinned.exists()


def test_a_platform_databricks_publishes_no_cli_for_fails_with_a_rule_id(
    pinned: Path, releases: Releases, project: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(pinned_cli, "CHECKSUMS", {"plan9_mips": "0" * 64})

    result = deploy(project)

    assert result.exit_code == 2
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "MSN913"
    assert pinned_cli.platform_name() in diagnostic["message"]
    assert releases.requests == []


def test_the_download_goes_through_the_proxy_the_environment_names(
    pinned: Path, releases: Releases, monkeypatch: pytest.MonkeyPatch
):
    # The fake server is the proxy too: a proxied request names the whole URL, not just a path.
    monkeypatch.setattr(pinned_cli, "RELEASES", "http://releases.example/download")
    monkeypatch.setenv("HTTP_PROXY", releases.url)
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

    pinned_cli.databricks()

    assert releases.requests == [
        f"http://releases.example/download/v{PINNED}/databricks_cli_{PINNED}_"
        f"{pinned_cli.platform_name()}.zip"
    ]


@pytest.mark.parametrize(
    ("system", "machine", "name", "binary"),
    [
        ("linux", "x86_64", "linux_amd64", "databricks"),
        ("linux", "aarch64", "linux_arm64", "databricks"),
        ("darwin", "x86_64", "darwin_amd64", "databricks"),
        ("darwin", "arm64", "darwin_arm64", "databricks"),
        ("win32", "AMD64", "windows_amd64", "databricks.exe"),
        ("win32", "ARM64", "windows_arm64", "databricks.exe"),
    ],
)
def test_this_release_pins_an_archive_for_every_platform_databricks_publishes(
    system: str, machine: str, name: str, binary: str
):
    assert pinned_cli.platform_name(system, machine) == name
    assert re.fullmatch("[0-9a-f]{64}", databricks_cli_release.CHECKSUMS[name])
    assert pinned_cli.binary_name(system) == binary


def test_mason_databricks_runs_the_pinned_cli_with_the_arguments_passed_through(
    pinned: Path, releases: Releases
):
    result = runner.invoke(cli.app, ["databricks", "auth", "describe", "--help", "-p", "x"])

    assert result.exit_code == 0, result.output
    assert pinned.read_text().splitlines() == ["auth describe --help -p x"]
    assert len(releases.requests) == 1


def test_mason_databricks_exits_with_the_clis_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    failing = tmp_path / "databricks"
    failing.write_text(f"#!/bin/sh\necho 'Databricks CLI v{pinned_cli.MINIMUM}'\nexit 3\n")
    failing.chmod(0o755)
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(failing))

    result = runner.invoke(cli.app, ["databricks", "bundle", "deploy"])

    assert result.exit_code == 3


def test_mason_version_names_the_cli_version_it_runs(pinned: Path, releases: Releases):
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0, result.output
    assert result.output == f"mason {version('mason-databricks')}\nDatabricks CLI {PINNED}\n"
    assert releases.requests == []


def test_mason_version_names_the_cli_mason_databricks_cli_points_at(
    pinned: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(pinned_cli.OVERRIDE, str(own_cli(tmp_path, "1.99.0")))

    result = runner.invoke(cli.app, ["--version"])

    assert result.output.endswith("Databricks CLI 1.99.0\n")


def test_the_databricks_on_the_path_is_never_run(
    pinned: Path, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    on_path = tmp_path / "bin"
    on_path.mkdir()
    (on_path / "databricks").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/path-calls\n')
    (on_path / "databricks").chmod(0o755)
    monkeypatch.setenv("PATH", f"{on_path}{os.pathsep}{os.environ['PATH']}")

    assert deploy(project).exit_code == 0
    assert runner.invoke(cli.app, ["databricks", "auth", "describe"]).exit_code == 0
    assert runner.invoke(cli.app, ["--version"]).exit_code == 0

    assert not (tmp_path / "path-calls").exists()
    assert "auth describe" in pinned.read_text()
