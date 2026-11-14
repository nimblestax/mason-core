"""The installed `brickie` command, run as a user runs it."""

import json
import subprocess
import sys
from pathlib import Path

BRICKIE = Path(sys.executable).parent / "brickie"


def brickie(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(BRICKIE), *args], capture_output=True, text=True)


def test_init_writes_brickie_platform_yaml(tmp_path: Path):
    result = brickie("init", str(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "brickie.platform.yaml").exists()


def test_validate_reports_an_unresolved_logical_name_as_brk201(tmp_path: Path):
    brickie("init", str(tmp_path))
    model = tmp_path / "domains/sales/models/gold/fct_orders.sql"
    model.write_text("SELECT * FROM sales.silver.nonexistent")

    result = brickie("validate", "--json", "--project", str(tmp_path))

    assert result.returncode == 1, result.stdout + result.stderr
    [diagnostic] = json.loads(result.stdout)["diagnostics"]
    assert diagnostic["rule"] == "BRK201"
