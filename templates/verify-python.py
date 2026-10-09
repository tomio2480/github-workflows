#!/usr/bin/env python3
"""Caller-owned Python gate. Run in the directory containing pyproject.toml.

The contract and customization points are in docs/python-lint.md.
"""

from __future__ import annotations

import argparse
import configparser
import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import metadata
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict


class Call(TypedDict):
    argv: list[str]
    stdout: str
    stderr: str
    exit_code: int | None


class Check(TypedDict):
    status: Literal["planned", "passed", "failed", "error", "not_applicable"]
    calls: NotRequired[list[Call]]
    reason: NotRequired[str]


class Report(TypedDict):
    schema_version: int
    project: str
    python: str
    platform: str
    executable: str
    checks: dict[str, Check]
    tool_versions: dict[str, str | None]
    status: NotRequired[str]
    error: NotRequired[str]
    targets: NotRequired[list[str]]
    declared_targets: NotRequired[list[str]]
    mypy_config: NotRequired[str | None]
    config_sha256: NotRequired[dict[str, str]]


def mypy_config(project: Path, tool: dict[str, Any]) -> str | None:
    section: dict[str, Any] | None
    for name in ("mypy.ini", ".mypy.ini", "pyproject.toml", "setup.cfg"):
        path = project / name
        if not path.is_file():
            continue
        if name == "pyproject.toml":
            section = tool.get("mypy")
        else:
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(path.read_text(encoding="utf-8"), source=name)
            section = dict(config["mypy"]) if config.has_section("mypy") else None
            if section is None and name != "setup.cfg":
                raise ValueError(f"{name}: [mypy] section is required")
        if section is not None:
            if not isinstance(section, dict) or not any(
                section.get(key) for key in ("files", "modules", "packages")
            ):
                raise ValueError(f"{name}: mypy requires files, modules, or packages")
            return name
    return None


def target_paths(project: Path, tool: dict[str, Any]) -> list[str]:
    quality = tool.get("python-quality", {})
    targets = quality.get("targets") if isinstance(quality, dict) else None
    if not isinstance(targets, list) or not targets:
        raise ValueError("tool.python-quality.targets must be a nonempty array")
    for target in targets:
        if (
            not isinstance(target, str)
            or not target
            or "\n" in target
            or "\r" in target
        ):
            raise ValueError("each target must be a nonempty path without newlines")
        path = Path(target)
        resolved = (project / path).resolve()
        if (
            path.is_absolute()
            or not resolved.is_relative_to(project)
            or not resolved.exists()
        ):
            raise ValueError(f"target must exist within the project: {target!r}")
    return targets


def batches(paths: list[str]) -> Iterator[list[str]]:
    batch: list[str] = []
    size = 0
    for path in paths:
        if batch and (size + len(path) > 6000 or len(batch) >= 100):
            yield batch
            batch, size = [], 0
        batch.append(path)
        size += len(path) + 3
    if batch:
        yield batch


@contextmanager
def attributed(check: Check) -> Iterator[None]:
    """Record an error on the check whose own step could not complete."""
    try:
        yield
    except (OSError, ValueError, configparser.Error):
        check["status"] = "error"
        raise


def reject_config_diagnostics(stderr: Path, project: Path, config: str) -> None:
    # mypy prints "<config>: ..." or "<config>:<line>: ..." for configuration problems,
    # with the absolute path of the file when show_absolute_path is set.
    # Some of them, such as unknown options, do not make it fail.
    names = "|".join(re.escape(name) for name in (config, str(project / config)))
    flags = re.IGNORECASE if sys.platform == "win32" else 0
    diagnostic = re.compile(rf"(?:{names}):(\d+:)*\s", flags)
    lines = stderr.read_text(encoding="utf-8", errors="replace").splitlines()
    if any(diagnostic.match(line) for line in lines):
        raise ValueError(f"mypy reported problems in {config}; see {stderr.name}")


def execute(argv: list[str], project: Path, directory: Path, check: Check) -> Path:
    index = len(list(directory.glob("*.stdout")))
    stdout = directory / f"{index:04}.stdout"
    stderr = directory / f"{index:04}.stderr"
    call: Call = {
        "argv": argv,
        "stdout": stdout.name,
        "stderr": stderr.name,
        "exit_code": None,
    }
    check.setdefault("calls", []).append(call)
    with stdout.open("wb") as out, stderr.open("wb") as err:
        result = subprocess.run(argv, cwd=project, stdout=out, stderr=err, check=False)
    call["exit_code"] = result.returncode
    if result.returncode != 0:
        check["status"] = "failed"
    elif check["status"] == "planned":
        check["status"] = "passed"
    return stdout


def run(project: Path, directory: Path, report: Report) -> int:
    checks = report["checks"]
    config_path = project / "pyproject.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    tool = config.get("tool", {})
    if not isinstance(tool, dict) or not isinstance(tool.get("ruff"), dict):
        raise ValueError("pyproject.toml requires [tool.ruff]")
    declared = target_paths(project, tool)
    report["declared_targets"] = declared
    with attributed(checks["mypy"]):
        selected_mypy = mypy_config(project, tool)
    report["mypy_config"] = selected_mypy
    report["config_sha256"] = {
        name: hashlib.sha256((project / name).read_bytes()).hexdigest()
        for name in dict.fromkeys(["pyproject.toml", "uv.lock", selected_mypy])
        if name and (project / name).is_file()
    }
    targets = set()
    discovery = checks["discovery"]
    with attributed(discovery):
        for target in declared:
            output = execute(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    "--config",
                    "pyproject.toml",
                    "--no-fix",
                    "--show-files",
                    "--",
                    target,
                ],
                project,
                directory,
                discovery,
            )
            if discovery["status"] == "failed":
                raise ValueError("Ruff target discovery failed; see its stdout/stderr")
            found = []
            for line in output.read_text(encoding="utf-8").splitlines():
                path = Path(line).resolve()
                if not path.is_relative_to(project) or not path.is_file():
                    raise ValueError(f"invalid discovered target: {line!r}")
                if path.suffix in (".py", ".pyi") and path != Path(__file__).resolve():
                    found.append(path.relative_to(project).as_posix())
            if not found:
                raise ValueError(f"no Python targets after Ruff exclusions: {target!r}")
            targets.update(found)
    report["targets"] = sorted(targets)
    # Explicit files keep lint and format on the same discovered set, even with force-exclude.
    for name, options in (
        ("lint", ["check", "--no-fix", "--no-unsafe-fixes"]),
        ("format", ["format", "--check"]),
    ):
        for batch in batches(report["targets"]):
            execute(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    *options,
                    "--config",
                    "pyproject.toml",
                    "--no-force-exclude",
                    "--",
                    *batch,
                ],
                project,
                directory,
                checks[name],
            )
    if selected_mypy:
        mypy = checks["mypy"]
        with attributed(mypy):
            execute(
                [sys.executable, "-m", "mypy", "--config-file", selected_mypy],
                project,
                directory,
                mypy,
            )
            reject_config_diagnostics(
                directory / mypy["calls"][-1]["stderr"], project, selected_mypy
            )
    else:
        checks["mypy"].update(
            {
                "status": "not_applicable",
                "reason": "no project-local mypy configuration",
            }
        )
    return int(
        any(
            check["status"] != "passed"
            for name, check in checks.items()
            if name != "mypy" or selected_mypy
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir", type=Path, default=Path(tempfile.gettempdir()) / "python-lint"
    )
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="run-", dir=args.report_dir)).resolve()
    project = Path.cwd().resolve()
    report: Report = {
        "schema_version": 1,
        "project": str(project),
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "checks": {
            name: {"status": "planned"}
            for name in ("discovery", "lint", "format", "mypy")
        },
        "tool_versions": {},
    }
    for name in ("ruff", "mypy"):
        try:
            report["tool_versions"][name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            report["tool_versions"][name] = None
    try:
        code = run(project, directory, report)
        report["status"] = "passed" if code == 0 else "failed"
    except (OSError, ValueError, configparser.Error) as exc:
        code = 2
        report.update({"status": "error", "error": str(exc)})
    path = directory / "report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary = ", ".join(
        f"{name}={check['status']}" for name, check in report["checks"].items()
    )
    print(f"Python quality: {report['status']} ({summary})")
    print(f"report: {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
