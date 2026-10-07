from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "templates/verify-python.py"


@pytest.fixture
def caller(tmp_path):
    project = tmp_path / "日本語 caller ' $ workspace"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src/example.py").write_text("value = 1\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        '[tool.python-quality]\ntargets = ["src"]\n'
        '[tool.ruff]\n[tool.mypy]\nfiles = ["src"]\n',
        encoding="utf-8",
    )
    fake = tmp_path / "fake_modules"
    fake.mkdir()
    source = """import json, os, pathlib, sys
name = pathlib.Path(__file__).stem
args = sys.argv[1:]
with open(os.environ["CALLS"], "a", encoding="utf-8") as log:
    log.write(json.dumps([name, *args]) + "\\n")
mode = os.environ.get("FAIL_MODE", "")
if name == "ruff" and "--show-files" in args:
    if mode != "empty":
        target = pathlib.Path(args[-1])
        paths = [target] if target.is_file() else sorted(target.rglob("*.py"))
        for path in paths:
            print(path.resolve())
    sys.exit(2 if mode == "discover" else 0)
if name == "mypy" and mode.startswith("mypy-"):
    config = args[args.index("--config-file") + 1]
    if mode == "mypy-stderr":
        print("plugin: informational note", file=sys.stderr)
        print("note: not a diagnostic of " + config + ": x", file=sys.stderr)
    else:
        print(config + ": [mypy]: Unrecognized option: bogus = True", file=sys.stderr)
    print("mypy passed")
    sys.exit(1 if mode == "mypy-config-types" else 0)
kind = "mypy" if name == "mypy" else ("format" if args[0] == "format" else "lint")
if mode == kind:
    print("diagnostic " * 10000)
    print("stderr marker", file=sys.stderr)
    sys.exit(1)
print(kind + " passed")
"""
    for name in ("ruff", "mypy"):
        (fake / f"{name}.py").write_text(source, encoding="utf-8")
    return project, fake


def invoke(caller, tmp_path, mode=""):
    project, fake = caller
    env = os.environ.copy()
    env.update(
        PYTHONUTF8="1",
        PYTHONPATH=str(fake),
        FAIL_MODE=mode,
        CALLS=str(tmp_path / "calls.jsonl"),
    )
    result = subprocess.run(
        [sys.executable, str(GATE), "--report-dir", str(tmp_path / "reports")],
        cwd=project,
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    reports = list((tmp_path / "reports").glob("*/report.json"))
    assert len(reports) == 1, (result.stdout, result.stderr)
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    return result, report, reports[0].parent


def calls(tmp_path):
    path = tmp_path / "calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def statuses(report):
    return {name: check["status"] for name, check in report["checks"].items()}


def test_all_checks_run_against_declared_project(caller, tmp_path):
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 0, result.stderr
    assert report["status"] == "passed"
    assert report["targets"] == ["src/example.py"]
    assert {k: v["status"] for k, v in report["checks"].items()} == {
        "discovery": "passed",
        "lint": "passed",
        "format": "passed",
        "mypy": "passed",
    }
    actual = calls(tmp_path)
    for kind in ("check", "format"):
        command = next(
            c for c in actual if c[:2] == ["ruff", kind] and "--show-files" not in c
        )
        assert command[-2:] == ["--", "src/example.py"]
        assert "--no-force-exclude" in command
        if kind == "check":
            assert "--no-fix" in command
            assert "--no-unsafe-fixes" in command
        else:
            assert "--check" in command
    assert actual[-1] == ["mypy", "--config-file", "pyproject.toml"]


@pytest.mark.parametrize("mode", ["lint", "format", "mypy"])
def test_failure_blocks_but_preserves_other_results_and_full_logs(
    caller, tmp_path, mode
):
    result, report, directory = invoke(caller, tmp_path, mode)
    assert result.returncode == 1
    assert report["status"] == "failed"
    assert report["checks"][mode]["status"] == "failed"
    assert all(c["status"] != "planned" for c in report["checks"].values())
    assert len(result.stdout) < 2000
    assert any(p.stat().st_size > 100000 for p in directory.glob("*.stdout"))
    assert any("stderr marker" in p.read_text() for p in directory.glob("*.stderr"))
    assert str(directory / "report.json") in result.stdout


@pytest.mark.parametrize("mode", ["empty", "discover"])
def test_discovery_cannot_succeed_without_targets(caller, tmp_path, mode):
    result, report, _ = invoke(caller, tmp_path, mode)
    assert result.returncode == 2
    assert report["status"] == "error"
    assert report["checks"]["discovery"]["status"] == "error"
    assert report["checks"]["lint"]["status"] == "planned"
    assert all("--show-files" in c for c in calls(tmp_path))


@pytest.mark.parametrize(
    "targets", ["[]", '["missing"]', '["../outside"]', "[1]", '"src"']
)
def test_invalid_targets_fail_before_tools(caller, tmp_path, targets):
    project, _ = caller
    config = project / "pyproject.toml"
    config.write_text(
        "[tool.python-quality]\ntargets = " + targets + "\n[tool.ruff]\n",
        encoding="utf-8",
    )
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 2
    assert "target" in report["error"].lower()
    assert set(statuses(report).values()) == {"planned"}
    assert not (tmp_path / "calls.jsonl").exists()


@pytest.mark.parametrize(
    "content", [None, "[broken", '[tool.python-quality]\ntargets = ["src"]\n']
)
def test_missing_or_invalid_config_is_error(caller, tmp_path, content):
    project, _ = caller
    config = project / "pyproject.toml"
    if content is None:
        config.unlink()
    else:
        config.write_text(content, encoding="utf-8")
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 2
    assert report["status"] == "error"
    assert set(statuses(report).values()) == {"planned"}
    assert not (tmp_path / "calls.jsonl").exists()


def test_mypy_absence_is_explicitly_not_applicable(caller, tmp_path):
    project, _ = caller
    config = project / "pyproject.toml"
    config.write_text(config.read_text().split("[tool.mypy]")[0], encoding="utf-8")
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 0
    assert report["checks"]["mypy"]["status"] == "not_applicable"
    assert report["checks"]["mypy"]["reason"]
    assert not any(c[0] == "mypy" for c in calls(tmp_path))


@pytest.mark.parametrize("filename", ["mypy.ini", ".mypy.ini", "setup.cfg"])
def test_local_mypy_config_enables_check(caller, tmp_path, filename):
    project, _ = caller
    config = project / "pyproject.toml"
    config.write_text(config.read_text().split("[tool.mypy]")[0], encoding="utf-8")
    (project / filename).write_text("[mypy]\nfiles = src\n", encoding="utf-8")
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 0
    assert calls(tmp_path)[-1] == ["mypy", "--config-file", filename]
    assert report["checks"]["mypy"]["status"] == "passed"


@pytest.mark.parametrize(
    "content", ["[mypy]\nstrict = True\n", "[other]\nkey = 1\n", "files = src\n"]
)
def test_mypy_config_without_targets_is_not_silently_skipped(caller, tmp_path, content):
    project, _ = caller
    (project / "mypy.ini").write_text(content, encoding="utf-8")
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 2
    assert "mypy.ini" in report["error"]
    # The failure is in mypy's own configuration; Ruff discovery never ran.
    assert statuses(report) == {
        "discovery": "planned",
        "lint": "planned",
        "format": "planned",
        "mypy": "error",
    }
    assert not (tmp_path / "calls.jsonl").exists()


@pytest.mark.parametrize("filename", ["pyproject.toml", "mypy.ini"])
@pytest.mark.parametrize(
    ("mode", "mypy_exit"), [("mypy-config", 0), ("mypy-config-types", 1)]
)
def test_mypy_config_diagnostic_is_error_regardless_of_exit_code(
    caller, tmp_path, filename, mode, mypy_exit
):
    project, _ = caller
    if filename == "mypy.ini":
        config = project / "pyproject.toml"
        config.write_text(config.read_text().split("[tool.mypy]")[0], encoding="utf-8")
        (project / filename).write_text("[mypy]\nfiles = src\n", encoding="utf-8")
    result, report, directory = invoke(caller, tmp_path, mode)
    assert result.returncode == 2
    assert report["status"] == "error"
    assert statuses(report) == {
        "discovery": "passed",
        "lint": "passed",
        "format": "passed",
        "mypy": "error",
    }
    call = report["checks"]["mypy"]["calls"][-1]
    assert call["argv"][-2:] == ["--config-file", filename]
    assert call["exit_code"] == mypy_exit
    assert filename in report["error"]
    assert call["stderr"] in report["error"]
    stderr = (directory / call["stderr"]).read_text(encoding="utf-8")
    assert "Unrecognized option" in stderr


def test_unrelated_mypy_stderr_is_not_a_config_error(caller, tmp_path):
    result, report, directory = invoke(caller, tmp_path, "mypy-stderr")
    assert result.returncode == 0, result.stderr
    assert report["checks"]["mypy"]["status"] == "passed"
    call = report["checks"]["mypy"]["calls"][-1]
    stderr = (directory / call["stderr"]).read_text(encoding="utf-8")
    assert "informational note" in stderr


def test_unknown_cli_option_is_rejected(caller):
    result = subprocess.run(
        [sys.executable, str(GATE), "--unknown"],
        cwd=caller[0],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_missing_tool_is_error_and_leaves_checks_unexecuted(caller, tmp_path):
    isolated = tmp_path / "isolated-python"
    venv.EnvBuilder(with_pip=False).create(isolated)
    executable = isolated / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    result = subprocess.run(
        [str(executable), str(GATE), "--report-dir", str(tmp_path / "reports")],
        cwd=caller[0],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 2, result.stdout
    path = next((tmp_path / "reports").glob("*/report.json"))
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["checks"]["discovery"]["status"] == "error"
    assert report["checks"]["lint"]["status"] == "planned"
    assert report["tool_versions"]["ruff"] is None
    assert "No module named ruff" in (path.parent / "0000.stderr").read_text()


def test_large_target_set_is_batched_without_losing_files(caller, tmp_path):
    for index in range(150):
        (caller[0] / "src" / f"日本語 space '$ {index}.py").write_text(
            "value = 1\n", encoding="utf-8"
        )
    result, report, _ = invoke(caller, tmp_path)
    assert result.returncode == 0
    assert len(report["targets"]) == 151
    lint_calls = [
        c
        for c in calls(tmp_path)
        if c[:2] == ["ruff", "check"] and "--show-files" not in c
    ]
    assert len(lint_calls) >= 2
    assert [
        target
        for command in lint_calls
        for target in command[command.index("--") + 1 :]
    ] == report["targets"]
