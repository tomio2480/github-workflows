#!/usr/bin/env python3
"""Probe the toolchain installed by the reusable Shell quality workflow."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args()
    if not args.require_all:
        parser.error("--require-all is required")

    for executable in ("shellcheck", "shfmt", "bats", "pwsh"):
        if shutil.which(executable) is None:
            print(f"missing tool: {executable}", file=sys.stderr)
            return 1

    probe = Path(__file__).with_name("probe-modules.ps1")
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(probe)],
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
