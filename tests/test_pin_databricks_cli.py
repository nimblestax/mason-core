"""The script that pins the Databricks CLI a release runs, against a fake of its releases."""

import runpy
import subprocess
import sys
from pathlib import Path

PIN = Path(__file__).parents[1] / "scripts" / "pin_databricks_cli.py"
PLATFORMS = [
    "darwin_amd64",
    "darwin_arm64",
    "linux_amd64",
    "linux_arm64",
    "windows_amd64",
    "windows_arm64",
]


def publish(releases: Path, version: str, platforms: list[str]) -> None:
    """A release's checksums file, as Databricks publishes it: a zip and a tarball per platform."""
    folder = releases / f"v{version}"
    folder.mkdir(parents=True)
    lines = []
    for number, name in enumerate(platforms):
        lines.append(f"{number:064x}  databricks_cli_{version}_{name}.tar.gz")
        lines.append(f"{number + 100:064x}  databricks_cli_{version}_{name}.zip")
    (folder / f"databricks_cli_{version}_SHA256SUMS").write_text("\n".join(lines) + "\n")


def pin(releases: Path, version: str, written: Path) -> subprocess.CompletedProcess[str]:
    arguments = [version, "--releases", releases.as_uri(), "--write", str(written)]
    return subprocess.run([sys.executable, str(PIN), *arguments], capture_output=True, text=True)


def test_the_version_and_each_platforms_zip_checksum_are_written(tmp_path: Path):
    publish(tmp_path / "releases", "1.30.0", PLATFORMS)
    written = tmp_path / "databricks_cli_release.py"

    result = pin(tmp_path / "releases", "1.30.0", written)

    assert result.returncode == 0, result.stderr
    pinned = runpy.run_path(str(written))
    assert pinned["VERSION"] == "1.30.0"
    assert pinned["CHECKSUMS"] == {
        name: f"{number + 100:064x}" for number, name in enumerate(PLATFORMS)
    }


def test_a_release_missing_a_platform_is_refused_and_nothing_is_written(tmp_path: Path):
    publish(tmp_path / "releases", "1.30.0", PLATFORMS[:-1])
    written = tmp_path / "databricks_cli_release.py"

    result = pin(tmp_path / "releases", "1.30.0", written)

    assert result.returncode == 1
    assert "windows_arm64" in result.stderr
    assert not written.exists()


def test_the_committed_pin_is_what_the_script_writes():
    """The committed file is never edited by hand, so it reads exactly as the script writes it."""
    committed = Path(__file__).parents[1] / "src/mason/deploy/databricks_cli_release.py"
    pinned = runpy.run_path(str(committed))
    script = runpy.run_path(str(PIN))

    assert committed.read_text() == script["render"](pinned["VERSION"], pinned["CHECKSUMS"])
