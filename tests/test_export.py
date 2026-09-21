"""Guard the one property the freshness check depends on: a stable export.

If `export_openapi.py` ever produces different bytes for the same code, every
build fails the freshness check and the whole gate gets ignored. These tests
are cheap insurance against that.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "export_openapi.py"


def run_export() -> bytes:
    """Run the exporter in a fresh process, exactly as api-guard does."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--stdout"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_export_is_byte_stable_across_processes() -> None:
    """Two separate runs must agree byte for byte.

    Run as subprocesses rather than calling generate() twice in-process: hash
    randomisation and dict ordering only differ across interpreters, so an
    in-process comparison would pass even if the output were unstable.
    """
    assert run_export() == run_export()


def test_export_uses_lf_line_endings() -> None:
    """CRLF would differ from the committed file on Windows and fail freshness."""
    assert b"\r\n" not in run_export()


def test_export_is_valid_yaml_describing_the_api() -> None:
    spec = yaml.safe_load(run_export())
    assert spec["openapi"].startswith("3.")
    assert set(spec["paths"]) == {"/users", "/users/{user_id}", "/health"}


@pytest.mark.parametrize("status", ["200", "404"])
def test_get_user_declares_its_error_responses(status: str) -> None:
    """Undeclared statuses fail Schemathesis' status_code_conformance check."""
    spec = yaml.safe_load(run_export())
    assert status in spec["paths"]["/users/{user_id}"]["get"]["responses"]
