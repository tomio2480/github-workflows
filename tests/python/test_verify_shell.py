"""bin/verify-shell.py（中央リポジトリ自身の Shell quality gate）の単体テスト．"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GATE = REPO_ROOT / "bin" / "verify-shell.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_shell", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_shell = _load_gate()


class RecordingRunner:
    """runner へ渡された argv を記録し，指定の終了コードを返す．"""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, argv) -> int:
        self.calls.append(list(argv))
        return self.returncode


def test_requires_require_all() -> None:
    completed = subprocess.run(
        [sys.executable, str(GATE)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "--require-all is required" in completed.stderr


def test_collect_targets_returns_sorted_repo_relative_paths() -> None:
    targets = verify_shell.collect_targets(REPO_ROOT, verify_shell.BASH_PATTERNS)

    assert targets == sorted(targets)
    assert "bin/release-patch.sh" in targets
    assert "scripts/post-lint-summary.sh" in targets
    assert all(target.endswith(".sh") for target in targets)
    assert all((REPO_ROOT / target).is_file() for target in targets)


def test_collect_targets_excludes_fixture_assets() -> None:
    targets = verify_shell.collect_targets(
        REPO_ROOT, verify_shell.POWERSHELL_PATTERNS
    )

    assert targets == [
        "bin/analyze-powershell.ps1",
        "bin/release-patch.ps1",
        "bin/watch-pr-checks.ps1",
    ]


def test_missing_tools_reports_absent_executables() -> None:
    missing = verify_shell.missing_tools(("shellcheck", "shfmt"), which=lambda _: None)

    assert missing == ["shellcheck", "shfmt"]


def test_missing_tools_is_empty_when_all_present() -> None:
    missing = verify_shell.missing_tools(
        ("shellcheck",), which=lambda name: f"/usr/bin/{name}"
    )

    assert missing == []


def test_run_shellcheck_passes_targets_as_argv() -> None:
    runner = RecordingRunner()

    returncode = verify_shell.run_shellcheck(["scripts/a.sh"], runner=runner)

    assert returncode == 0
    assert runner.calls == [["shellcheck", "scripts/a.sh"]]


def test_run_shfmt_checks_diff_with_repo_format_options() -> None:
    runner = RecordingRunner(returncode=1)

    returncode = verify_shell.run_shfmt(["scripts/a.sh"], runner=runner)

    assert returncode == 1
    assert runner.calls == [["shfmt", "-d", "-i", "2", "-ci", "scripts/a.sh"]]


def test_run_powershell_analyzer_invokes_pwsh_with_script_file() -> None:
    runner = RecordingRunner()

    returncode = verify_shell.run_powershell_analyzer(
        ["bin/release-patch.ps1"], runner=runner
    )

    assert returncode == 0
    assert runner.calls == [
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(verify_shell.ANALYZER_SCRIPT),
            "bin/release-patch.ps1",
        ]
    ]


def test_run_checks_reports_every_failure() -> None:
    runner = RecordingRunner(returncode=1)

    returncode = verify_shell.run_checks(runner=runner)

    assert returncode == 1
    assert [call[0] for call in runner.calls] == ["shellcheck", "shfmt", "pwsh"]


def test_run_checks_prints_inspected_targets(capsys) -> None:
    verify_shell.run_checks(runner=RecordingRunner())

    captured = capsys.readouterr().out
    assert "scripts/post-lint-summary.sh" in captured
    assert "bin/release-patch.ps1" in captured


def test_run_checks_succeeds_when_every_tool_succeeds() -> None:
    runner = RecordingRunner(returncode=0)

    assert verify_shell.run_checks(runner=runner) == 0


def test_main_fails_when_required_tool_is_missing() -> None:
    environment = os.environ.copy()
    environment["PATH"] = ""

    completed = subprocess.run(
        [sys.executable, str(GATE), "--require-all"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode != 0
    assert "missing tool" in completed.stderr
