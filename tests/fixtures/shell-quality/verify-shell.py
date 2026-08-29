#!/usr/bin/env python3
"""Probe the toolchain installed by the reusable Shell quality workflow."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


EXPECTED_VERSIONS = {
    "shellcheck": (["shellcheck", "--version"], "version: 0.11.0"),
    "shfmt": (["shfmt", "--version"], "v3.13.1"),
    "bats": (["bats", "--version"], "Bats 1.14.0"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    if not args.require_all:
        parser.error("--require-all is required")

    for executable in (*EXPECTED_VERSIONS, "pwsh"):
        if shutil.which(executable) is None:
            print(f"missing tool: {executable}", file=sys.stderr)
            return 1

    for executable, (argv, expected_line) in EXPECTED_VERSIONS.items():
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
        )
        version_lines = completed.stdout.splitlines()
        if completed.returncode != 0 or expected_line not in version_lines:
            print(
                f"unexpected {executable} version: {completed.stdout.strip()}",
                file=sys.stderr,
            )
            return 1

    probe = Path(__file__).with_name("probe-modules.ps1")
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(probe)],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
