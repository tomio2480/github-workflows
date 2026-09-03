#!/usr/bin/env python3
"""github-workflows 自身のシェル資産を検査する repo-local Shell quality gate.

`.github/workflows/shell-quality.yml` の caller contract に従う．

    python bin/verify-shell.py --require-all

検査対象と実行するツールは本リポジトリの責務として本ファイルが決める．
中央 workflow は toolchain の配置だけを担う（docs/shell-quality.md 参照）．

Bats は `test-self-lint.yml` の unit-bash job が同じ suite を実行するため
本 gate では動かさない．Pester は `tests/powershell/*.Tests.ps1` を対象に
本 gate から実行する．bats を持たない PowerShell 版の振る舞いを担保する．
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ANALYZER_SCRIPT = REPO_ROOT / "bin" / "analyze-powershell.ps1"
PESTER_SCRIPT = REPO_ROOT / "bin" / "run-pester.ps1"

BASH_PATTERNS = ("bin/*.sh", "scripts/*.sh")
# bin/lib/ は dot-source して使う共有ヘルパーを置く．実行はしないが
# 振る舞いを持つため，静的解析の対象からは外さない．
POWERSHELL_PATTERNS = ("bin/*.ps1", "bin/lib/*.ps1")
PESTER_PATTERNS = ("tests/powershell/*.Tests.ps1",)

# 既存スクリプトの整形規則．-i 2 はインデント幅，-ci は case 分岐のインデント．
SHFMT_OPTIONS = ("-i", "2", "-ci")

REQUIRED_TOOLS = ("shellcheck", "shfmt", "pwsh")

Runner = Callable[[Sequence[str]], int]


def default_runner(argv: Sequence[str]) -> int:
    """argv 配列でプロセスを起動し終了コードを返す．出力は素通しする．"""
    completed = subprocess.run(list(argv), check=False, cwd=REPO_ROOT)
    return completed.returncode


def collect_targets(root: Path, patterns: Iterable[str]) -> list[str]:
    """パターンに一致するファイルを repo 相対の POSIX パスで返す．"""
    targets: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                targets.add(path.relative_to(root).as_posix())
    return sorted(targets)


def missing_tools(
    tools: Iterable[str],
    which: Callable[[str], str | None] = shutil.which,
) -> list[str]:
    """PATH 上に見つからない実行ファイル名を返す．"""
    return [tool for tool in tools if which(tool) is None]


def run_shellcheck(targets: Sequence[str], runner: Runner) -> int:
    if not targets:
        return 0
    return runner(["shellcheck", *targets])


def run_shfmt(targets: Sequence[str], runner: Runner) -> int:
    if not targets:
        return 0
    return runner(["shfmt", "-d", *SHFMT_OPTIONS, *targets])


def run_powershell_analyzer(targets: Sequence[str], runner: Runner) -> int:
    if not targets:
        return 0
    return runner(
        ["pwsh", "-NoProfile", "-File", str(ANALYZER_SCRIPT), *targets]
    )


def run_pester(targets: Sequence[str], runner: Runner) -> int:
    if not targets:
        return 0
    return runner(["pwsh", "-NoProfile", "-File", str(PESTER_SCRIPT), *targets])


def run_checks(runner: Runner = default_runner) -> int:
    """全チェックを実行する．途中で打ち切らず，失敗を集約して返す．"""
    bash_targets = collect_targets(REPO_ROOT, BASH_PATTERNS)
    powershell_targets = collect_targets(REPO_ROOT, POWERSHELL_PATTERNS)
    pester_targets = collect_targets(REPO_ROOT, PESTER_PATTERNS)

    # 「チェックが pass した」と「対象を検査した」を CI ログ上で区別するため，
    # ShellCheck と shfmt が無出力で成功する場合でも対象を残す．
    # 子プロセスの出力と混ざらないよう flush する．
    print(f"targets (shellcheck, shfmt): {', '.join(bash_targets)}", flush=True)
    print(f"targets (PSScriptAnalyzer): {', '.join(powershell_targets)}", flush=True)
    print(f"targets (Pester): {', '.join(pester_targets)}", flush=True)

    exit_codes = [
        run_shellcheck(bash_targets, runner),
        run_shfmt(bash_targets, runner),
        run_powershell_analyzer(powershell_targets, runner),
        run_pester(pester_targets, runner),
    ]
    return 0 if all(code == 0 for code in exit_codes) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-all", action="store_true")
    args = parser.parse_args(argv)
    if not args.require_all:
        parser.error("--require-all is required")

    absent = missing_tools(REQUIRED_TOOLS)
    if absent:
        print(f"missing tool: {', '.join(absent)}", file=sys.stderr)
        return 1

    return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
