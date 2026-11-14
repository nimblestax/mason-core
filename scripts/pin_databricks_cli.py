"""Pin the Databricks CLI version Brickie runs, with each platform's checksum.

    pin_databricks_cli.py <version>

Reads the checksums Databricks publishes with that release and writes them, with the version,
into Brickie. Commit what changes, so bumping the CLI is one pull request.
"""

import argparse
import sys
import urllib.request
from pathlib import Path

RELEASES = "https://github.com/databricks/cli/releases/download"
PINNED = Path(__file__).parents[1] / "src/brickie/deploy/databricks_cli_release.py"

# Every platform Databricks publishes a CLI for. A release missing one is refused.
PLATFORMS = [
    "darwin_amd64",
    "darwin_arm64",
    "linux_amd64",
    "linux_arm64",
    "windows_amd64",
    "windows_arm64",
]


class Refused(Exception):
    pass


def checksums(releases: str, version: str) -> dict[str, str]:
    """Each platform's zip checksum, from the release's published SHA256SUMS file."""
    url = f"{releases}/v{version}/databricks_cli_{version}_SHA256SUMS"
    with urllib.request.urlopen(url, timeout=60) as response:
        published = response.read().decode()
    found = {}
    for line in published.splitlines():
        checksum, archive = line.split()
        prefix, suffix = f"databricks_cli_{version}_", ".zip"
        if archive.startswith(prefix) and archive.endswith(suffix):
            found[archive.removeprefix(prefix).removesuffix(suffix)] = checksum
    missing = [name for name in PLATFORMS if name not in found]
    if missing:
        raise Refused(f"{url} has no zip archive for {', '.join(missing)}.")
    return {name: found[name] for name in PLATFORMS}


def render(version: str, pinned: dict[str, str]) -> str:
    rows = "".join(f'    "{name}": "{checksum}",\n' for name, checksum in pinned.items())
    return (
        '"""The Databricks CLI this Brickie release runs. Written by `just release::pin-cli`;'
        ' don\'t edit."""\n'
        "\n"
        f'VERSION = "{version}"\n'
        "\n"
        "# The SHA-256 of each platform's zip archive, from the release's published checksums.\n"
        f"CHECKSUMS = {{\n{rows}}}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="The Databricks CLI version, such as 1.23.0.")
    parser.add_argument("--releases", default=RELEASES, help=argparse.SUPPRESS)
    parser.add_argument("--write", type=Path, default=PINNED, help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    version = arguments.version.removeprefix("v")
    try:
        pinned = checksums(arguments.releases, version)
    except Refused as refused:
        print(refused, file=sys.stderr)
        return 1
    arguments.write.write_text(render(version, pinned))
    print(f"Pinned Databricks CLI {version} in {arguments.write}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
