"""The Databricks CLI Brickie runs: its own pinned version, downloaded once and cached per version.

Every call goes through the binary this module returns, by absolute path, so the `databricks` on
the PATH is never used and every machine deploys with the same CLI.
"""

import hashlib
import io
import os
import platform
import re
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from brickie.deploy.databricks_cli_release import CHECKSUMS, VERSION
from brickie.diagnostics import USAGE_OR_ENVIRONMENT, Failure, error

RELEASES = "https://github.com/databricks/cli/releases/download"
# Names a Databricks CLI to run instead, for a machine that can't download one.
OVERRIDE = "BRICKIE_DATABRICKS_CLI"
# The oldest Databricks CLI this release is tested with. An override older than this is refused.
MINIMUM = "1.23.0"
DOWNLOAD_TIMEOUT_SECONDS = 120

# How each OS and architecture is named in Databricks' archive names.
OPERATING_SYSTEMS = {"darwin": "darwin", "linux": "linux", "win32": "windows"}
ARCHITECTURES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


def databricks() -> Path:
    """The Databricks CLI to run, downloaded and checked first if this machine hasn't got it."""
    override = os.environ.get(OVERRIDE)
    if override:
        return _checked(Path(override).absolute())
    binary = cache_folder() / VERSION / binary_name()
    if binary.exists():
        return binary
    binary.parent.mkdir(parents=True, exist_ok=True)
    with _locked(binary.parent / "install.lock"):
        if not binary.exists():  # Another run may have installed it while this one waited.
            _install(binary)
    return binary


def running_version() -> str:
    """The version of the Databricks CLI Brickie runs, with no download."""
    override = os.environ.get(OVERRIDE)
    return _version_of(Path(override).absolute()) if override else VERSION


def _version_of(executable: Path) -> str:
    """The version a Databricks CLI reports, such as `1.23.0`."""
    try:
        printed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=60
        ).stdout
    except OSError as failure:  # Missing, or not something this machine can run.
        found = error(
            "BRK903",
            "",
            f"{OVERRIDE} names {executable}, which Brickie can't run: {failure.strerror}.",
            f"Point {OVERRIDE} at a Databricks CLI, or unset it so Brickie downloads its own.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT) from failure
    reported = re.search(r"(\d+)\.(\d+)\.(\d+)", printed)
    return reported.group(0) if reported else ""


def _checked(executable: Path) -> Path:
    """The CLI `BRICKIE_DATABRICKS_CLI` names, refused when it's older than this release
    supports."""
    found = _version_of(executable)
    if found and _parts(found) >= _parts(MINIMUM):
        return executable
    reported = f"is version {found}" if found else "doesn't say which version it is"
    problem = error(
        "BRK911",
        "",
        f"{OVERRIDE} names {executable}, which {reported}. This Brickie needs {MINIMUM} or newer.",
        f"Point {OVERRIDE} at Databricks CLI {VERSION}, the version this Brickie downloads, or"
        " unset it.",
    )
    raise Failure([problem], USAGE_OR_ENVIRONMENT)


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def platform_name(system: str = sys.platform, machine: str = platform.machine()) -> str:
    """This machine as Databricks names it in an archive, such as `darwin_arm64`."""
    return f"{OPERATING_SYSTEMS.get(system, system)}_{ARCHITECTURES.get(machine.lower(), machine)}"


def binary_name(system: str = sys.platform) -> str:
    return "databricks.exe" if system == "win32" else "databricks"


def cache_folder() -> Path:
    """Where downloaded CLIs are kept, one folder per version, in the user's cache folder."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "brickie" / "databricks-cli"


def _install(binary: Path) -> None:
    name = platform_name()
    if name not in CHECKSUMS:
        found = error(
            "BRK913",
            "",
            f"Databricks publishes no CLI for this machine, {name}.",
            f"Install a Databricks CLI yourself and point {OVERRIDE} at it.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)
    url = f"{RELEASES}/v{VERSION}/databricks_cli_{VERSION}_{name}.zip"
    downloaded = _download(url)
    if hashlib.sha256(downloaded).hexdigest() != CHECKSUMS[name]:
        found = error(
            "BRK910",
            "",
            f"The Databricks CLI {VERSION} downloaded from {url} doesn't match its checksum,"
            " so Brickie ran nothing.",
            "Run the command again. If it fails again, something between you and GitHub is"
            f" changing the download: check your proxy, or point {OVERRIDE} at a Databricks CLI"
            " you installed yourself.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT)
    unpacked = binary.with_name(f"{binary.name}.partial")
    with zipfile.ZipFile(io.BytesIO(downloaded)) as archive:
        unpacked.write_bytes(archive.read(binary.name))
    unpacked.chmod(0o755)
    # Renamed into place last, so an interrupted install never leaves a half-written CLI.
    unpacked.replace(binary)


def _download(url: str) -> bytes:
    # A new opener reads HTTPS_PROXY and NO_PROXY as they are now; `urlopen` keeps its first.
    opener = urllib.request.build_opener()
    try:
        with opener.open(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            return response.read()
    except OSError as failure:  # URLError, HTTPError and timeouts are all OSErrors.
        found = error(
            "BRK912",
            "",
            f"Brickie couldn't download the Databricks CLI {VERSION} from {url}: {failure}.",
            "Check this machine can reach github.com, through HTTPS_PROXY if it needs one."
            f" Without access, install the CLI yourself and point {OVERRIDE} at it.",
        )
        raise Failure([found], USAGE_OR_ENVIRONMENT) from failure


@contextmanager
def _locked(path: Path) -> Generator[None]:
    """Holds a lock on `path` across processes, so two runs never download at once."""
    with path.open("a") as handle:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:  # LK_LOCK gives up after ten seconds; a download takes longer.
                    continue
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        yield  # Closing the file releases the lock.
