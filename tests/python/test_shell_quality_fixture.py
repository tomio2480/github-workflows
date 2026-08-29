from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "shell-quality"
    / "verify-shell.py"
)


def test_fixture_requires_require_all() -> None:
    completed = subprocess.run(
        [sys.executable, str(FIXTURE)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "--require-all is required" in completed.stderr


def test_require_all_rejects_missing_tool() -> None:
    environment = os.environ.copy()
    environment["PATH"] = ""

    completed = subprocess.run(
        [sys.executable, str(FIXTURE), "--require-all"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert "missing tool: shellcheck" in completed.stderr
