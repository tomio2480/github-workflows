from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/python-quality"
GATE = ROOT / "templates/verify-python.py"


@pytest.mark.parametrize(
    ("case", "exit_code", "check", "status"),
    [
        ("green", 0, "mypy", "passed"),
        ("lint", 1, "lint", "failed"),
        ("format", 1, "format", "failed"),
        ("types", 1, "mypy", "failed"),
        ("no-mypy", 0, "mypy", "not_applicable"),
        ("empty", 2, "discovery", "error"),
        ("excluded", 2, "discovery", "error"),
        ("format-excluded", 1, "format", "failed"),
        ("mypy-no-target", 1, "mypy", "failed"),
    ],
)
def test_real_tools(tmp_path, case, exit_code, check, status):
    project = tmp_path / "日本語 project ' $"
    project.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy(FIXTURE / name, project / name)
    shutil.copytree(FIXTURE / "src", project / "src")
    shutil.copytree(FIXTURE / "tests", project / "tests")
    source = project / "src/quality_example.py"
    config = project / "pyproject.toml"
    if case == "lint":
        source.write_text("import os\n\n" + source.read_text(), encoding="utf-8")
    elif case in ("format", "format-excluded"):
        source.write_text("label = 'value'\n\n" + source.read_text(), encoding="utf-8")
    elif case == "types":
        source.write_text(
            source.read_text().replace("return value", 'return "wrong"'),
            encoding="utf-8",
        )
    elif case == "no-mypy":
        config.write_text(config.read_text().split("[tool.mypy]")[0], encoding="utf-8")
    elif case == "empty":
        source.unlink()
    elif case == "excluded":
        config.write_text(
            config.read_text().replace(
                "[tool.ruff]", '[tool.ruff]\nexclude = ["src/**"]'
            ),
            encoding="utf-8",
        )
    elif case == "mypy-no-target":
        config.write_text(
            config.read_text().replace(
                'files = ["src", "tests"]', 'files = ["missing/**/*.py"]'
            ),
            encoding="utf-8",
        )
    if case == "format-excluded":
        config.write_text(
            config.read_text().replace(
                "[tool.ruff]", "[tool.ruff]\nforce-exclude = true"
            )
            + '\n[tool.ruff.format]\nexclude = ["src/**"]\n',
            encoding="utf-8",
        )
    before = {p: p.read_bytes() for p in project.rglob("*.py")}
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, str(GATE), "--report-dir", str(tmp_path / "reports")],
        cwd=project,
        env=env,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    reports = list((tmp_path / "reports").glob("*/report.json"))
    assert len(reports) == 1, result.stderr
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    assert result.returncode == exit_code, (result.stdout, report)
    assert report["checks"][check]["status"] == status
    assert all(p.read_bytes() == data for p, data in before.items())
