#!/usr/bin/env python3
"""caller repo の Shell quality gate 雛形．`bin/verify-shell.py` として配置する．

`.github/workflows/shell-quality.yml`（reusable workflow）の caller contract に従う．

    python bin/verify-shell.py --require-all

中央 workflow は toolchain の配置だけを担う．
何を検査するかは caller repo の責務であり，本ファイルが決める．
下の「設定」節を自分の repo に合わせて書き換える．

雛形は中央リポジトリの `bin/verify-shell.py` の複製ではない．
あちらは中央固有の規律（native command の呼び出し検査・Pester）まで持つ．
雛形は ShellCheck・shfmt・PSScriptAnalyzer に絞る．
足りない検査は各 repo が自分の判断で足す．

Python 3.9 以上で動く．caller が workflow の `python-version` を下げても
そのまま使えるよう，実行時に評価される型注釈へ PEP 604 の `|` を持ち込まない．

導入と拡張の手順は，中央リポジトリの docs/shell-quality.md を参照する．
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Optional


# --- 設定（caller が書き換える） ---

# 検査対象の glob．repo root からの相対で書く．
# 対象が 1 つも無いと gate は失敗する．書き換え漏れを成功にしないためである．
BASH_PATTERNS = ("bin/*.sh", "scripts/*.sh")
POWERSHELL_PATTERNS = ("bin/*.ps1",)

# shfmt の整形規則．-i はインデント幅，-ci は case 分岐のインデント．
SHFMT_OPTIONS = ("-i", "2", "-ci")

# PSScriptAnalyzer の実行部．雛形と対で配布する．
ANALYZER_RELATIVE_PATH = "bin/analyze-powershell.ps1"

# --- 設定ここまで ---


REPO_ROOT = Path(__file__).resolve().parents[1]

BASH_TOOLS = ("shellcheck", "shfmt")
POWERSHELL_TOOLS = ("pwsh",)

Runner = Callable[[Sequence[str]], int]
# `str | None` を別名の右辺へ置かない．別名は import 時に評価されるため，
# `from __future__ import annotations` では遅延されず Python 3.9 で落ちる．
# 注釈の中でだけ使う．caller が python-version を下げても動くようにする．
Which = Callable[[str], Optional[str]]


def collect_targets(root: Path, patterns: Iterable[str]) -> list[str]:
    """パターンに一致するファイルを repo 相対の POSIX パスで返す．"""
    targets: set[str] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                targets.add(path.relative_to(root).as_posix())
    return sorted(targets)


def required_tools(
    bash_targets: Sequence[str], powershell_targets: Sequence[str]
) -> tuple[str, ...]:
    """実際に検査する対象へ対応するツールだけを必須とする．

    PowerShell 資産を持たない repo が pwsh 不足で落ちるのを避ける．
    逆に，対象があるのにツールが無い場合は失敗させる．
    検査を省くと，素通りと「指摘なし」を区別できなくなるためである．
    """
    tools: list[str] = []
    if bash_targets:
        tools.extend(BASH_TOOLS)
    if powershell_targets:
        tools.extend(POWERSHELL_TOOLS)
    return tuple(tools)


def missing_tools(tools: Iterable[str], which: Which = shutil.which) -> list[str]:
    """PATH 上に見つからない実行ファイル名を返す．"""
    return [tool for tool in tools if which(tool) is None]


def make_runner(cwd: Path) -> Runner:
    """argv 配列でプロセスを起動する runner を返す．出力は素通しする．

    command string を評価しない．引数へ空白や記号が入っても 1 引数のまま渡る．
    """

    def run(argv: Sequence[str]) -> int:
        completed = subprocess.run(list(argv), check=False, cwd=cwd)
        return completed.returncode

    return run


def run_shellcheck(targets: Sequence[str], runner: Runner) -> int:
    if not targets:
        return 0
    return runner(["shellcheck", *targets])


def run_shfmt(targets: Sequence[str], runner: Runner) -> int:
    if not targets:
        return 0
    return runner(["shfmt", "-d", *SHFMT_OPTIONS, *targets])


def run_powershell_analyzer(
    targets: Sequence[str], runner: Runner, root: Path
) -> int:
    if not targets:
        return 0
    analyzer = root / ANALYZER_RELATIVE_PATH
    return runner(["pwsh", "-NoProfile", "-File", str(analyzer), *targets])


def run_checks(
    runner: Runner | None = None,
    root: Path = REPO_ROOT,
    which: Which = shutil.which,
) -> int:
    """全チェックを実行する．途中で打ち切らず，失敗を集約して返す．"""
    if runner is None:
        runner = make_runner(root)

    bash_targets = collect_targets(root, BASH_PATTERNS)
    powershell_targets = collect_targets(root, POWERSHELL_PATTERNS)

    # 対象 0 件は「検査するものが無い」ではなく「パターンが合っていない」を疑う．
    # 成功にすると，glob の書き換え漏れが緑のまま残る．
    if not bash_targets and not powershell_targets:
        patterns = ", ".join((*BASH_PATTERNS, *POWERSHELL_PATTERNS))
        print(f"no target matched: {patterns}", file=sys.stderr, flush=True)
        return 1

    absent = missing_tools(required_tools(bash_targets, powershell_targets), which)
    if absent:
        print(f"missing tool: {', '.join(absent)}", file=sys.stderr, flush=True)
        return 1

    # 雛形だけコピーして helper を置き忘れると，pwsh 側の「ファイルが無い」
    # という失敗になる．何を置き忘れたのかが読み取れないため，先に名指しする．
    if powershell_targets and not (root / ANALYZER_RELATIVE_PATH).is_file():
        print(
            f"missing helper: {ANALYZER_RELATIVE_PATH} "
            "(templates/analyze-powershell.ps1 を配置する)",
            file=sys.stderr,
            flush=True,
        )
        return 1

    # 「チェックが pass した」と「対象を検査した」を CI ログ上で区別する．
    # 子プロセスの出力と混ざらないよう flush する．
    print(f"targets (shellcheck, shfmt): {', '.join(bash_targets)}", flush=True)
    print(f"targets (PSScriptAnalyzer): {', '.join(powershell_targets)}", flush=True)

    exit_codes = [
        run_shellcheck(bash_targets, runner),
        run_shfmt(bash_targets, runner),
        run_powershell_analyzer(powershell_targets, runner, root),
    ]

    return 0 if all(code == 0 for code in exit_codes) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument(
        "--powershell-only",
        action="store_true",
        help="windows job 用（本雛形は未実装）",
    )
    args = parser.parse_args(argv)
    if not args.require_all:
        parser.error("--require-all is required")

    if args.powershell_only:
        # 黙って無視すると，windows job が何も検査せず緑で終わる．
        print(
            "--powershell-only is not implemented in this template. "
            "windows-verify を有効にする repo は，Pester の実行と "
            "対象 0 件・skip の扱いを自分で足す．"
            "契約は docs/shell-quality.md「任意の windows job」節を参照．",
            file=sys.stderr,
        )
        return 2

    return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
