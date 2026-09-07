"""templates/verify-shell.py（caller 向け雛形）の単体テスト．

雛形は中央の `bin/verify-shell.py` と同期させない．
両者は検査対象も検査するツールも違うためである（Issue #149）．
代わりに，雛形が caller contract を満たすことと，
検査を素通りさせないことを本ファイルが固定する．
"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "verify-shell.py"
ANALYZER_TEMPLATE = REPO_ROOT / "templates" / "analyze-powershell.ps1"


def _load_template():
    spec = importlib.util.spec_from_file_location("templates_verify_shell", TEMPLATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_shell = _load_template()


class RecordingRunner:
    """runner へ渡された argv を記録し，指定の終了コードを返す．"""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[list[str]] = []

    def __call__(self, argv) -> int:
        self.calls.append(list(argv))
        return self.returncode


def _make_caller_repo(
    tmp_path: Path, *, bash: bool = False, powershell: bool = False
) -> Path:
    """雛形を配置した caller repo を tmp_path へ作る．

    `analyze-powershell.ps1` は PowerShell 資産を持つ repo だけが対で置く．
    置いた場合は自身も `bin/*.ps1` に入り，PSScriptAnalyzer の対象になる．
    """
    (tmp_path / "bin").mkdir()
    shutil.copy(TEMPLATE, tmp_path / "bin" / "verify-shell.py")
    if bash:
        (tmp_path / "bin" / "example.sh").write_text("#!/usr/bin/env bash\n")
    if powershell:
        shutil.copy(ANALYZER_TEMPLATE, tmp_path / "bin" / "analyze-powershell.ps1")
        (tmp_path / "bin" / "example.ps1").write_text("Write-Output 'ok'\n")
    return tmp_path


def _always_found(name: str) -> str:
    return f"/usr/bin/{name}"


# --- CLI contract（docs/shell-quality.md「導入」節） ---


def test_requires_require_all() -> None:
    completed = subprocess.run(
        [sys.executable, str(TEMPLATE)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "--require-all is required" in completed.stderr


def test_powershell_only_is_rejected_with_guidance() -> None:
    """雛形は windows contract を実装しない．黙って無視せず理由を出して落ちる．"""
    completed = subprocess.run(
        [sys.executable, str(TEMPLATE), "--require-all", "--powershell-only"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--powershell-only" in completed.stderr
    assert "docs/shell-quality.md" in completed.stderr


def test_end_to_end_fails_when_required_tool_is_missing(tmp_path) -> None:
    caller = _make_caller_repo(tmp_path, bash=True)
    environment = os.environ.copy()
    environment["PATH"] = ""

    completed = subprocess.run(
        [sys.executable, str(caller / "bin" / "verify-shell.py"), "--require-all"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode != 0
    assert "missing tool" in completed.stderr


# --- 必須ツールは実際の検査対象から決まる ---


def test_required_tools_covers_both_toolchains() -> None:
    assert verify_shell.required_tools(["bin/a.sh"], ["bin/a.ps1"]) == (
        "shellcheck",
        "shfmt",
        "pwsh",
    )


def test_required_tools_drops_powershell_without_powershell_targets() -> None:
    """PowerShell 資産を持たない caller が pwsh 不足で落ちてはならない．"""
    assert verify_shell.required_tools(["bin/a.sh"], []) == ("shellcheck", "shfmt")


def test_required_tools_drops_bash_tools_without_bash_targets() -> None:
    assert verify_shell.required_tools([], ["bin/a.ps1"]) == ("pwsh",)


# --- 対象 0 件を成功にしない ---


def test_run_checks_fails_when_nothing_matches(tmp_path) -> None:
    """パターンの書き換え漏れが「指摘 0 件で成功」に化けるのを止める．"""
    runner = RecordingRunner()

    returncode = verify_shell.run_checks(
        runner=runner, root=tmp_path, which=_always_found
    )

    assert returncode == 1
    assert runner.calls == []


def test_run_checks_reports_the_patterns_when_nothing_matches(tmp_path, capsys) -> None:
    verify_shell.run_checks(
        runner=RecordingRunner(), root=tmp_path, which=_always_found
    )

    captured = capsys.readouterr()
    assert "no target matched" in captured.err
    assert verify_shell.BASH_PATTERNS[0] in captured.err


def test_analyzer_helper_alone_does_not_count_as_a_target(tmp_path) -> None:
    """helper 自身を「検査対象がある」根拠にしない．

    配布した `bin/analyze-powershell.ps1` は既定の `POWERSHELL_PATTERNS` へ
    当たる．PowerShell 資産が `src/*.ps1` などにある caller が glob を
    書き換え忘れると，対象 0 件の guard を通り抜ける．
    helper だけを解析して緑で終わり，実資産は 1 つも検査されない．
    """
    caller = _make_caller_repo(tmp_path)
    shutil.copy(ANALYZER_TEMPLATE, caller / "bin" / "analyze-powershell.ps1")
    runner = RecordingRunner()

    returncode = verify_shell.run_checks(
        runner=runner, root=caller, which=_always_found
    )

    assert returncode == 1
    assert runner.calls == []


def test_analyzer_helper_is_still_analyzed_alongside_real_targets(tmp_path) -> None:
    """対象から外すのは「あるかどうか」の判定だけである．解析はする．"""
    caller = _make_caller_repo(tmp_path, powershell=True)
    runner = RecordingRunner()

    verify_shell.run_checks(runner=runner, root=caller, which=_always_found)

    assert runner.calls[-1][-2:] == [
        "bin/analyze-powershell.ps1",
        "bin/example.ps1",
    ]


# --- repo root は script の置き場所に依存させない ---


def test_repo_root_follows_git_toplevel(tmp_path) -> None:
    """`verify-script` を深い場所へ移しても repo root を見失わない．"""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    script_dir = tmp_path / ".github" / "scripts"
    script_dir.mkdir(parents=True)

    root = verify_shell.resolve_repo_root(script_dir)

    assert root.resolve() == tmp_path.resolve()


def test_repo_root_falls_back_to_the_parent_outside_git(tmp_path) -> None:
    """git が使えない環境では script の 1 つ上へ落とす．"""
    script_dir = tmp_path / "bin"
    script_dir.mkdir()

    root = verify_shell.resolve_repo_root(script_dir)

    assert root.resolve() == tmp_path.resolve()


# --- 対象に応じたツールだけを起動する ---


def test_run_checks_runs_only_bash_tools_for_a_bash_only_repo(tmp_path) -> None:
    caller = _make_caller_repo(tmp_path, bash=True)
    runner = RecordingRunner()

    returncode = verify_shell.run_checks(
        runner=runner, root=caller, which=_always_found
    )

    assert returncode == 0
    assert [call[0] for call in runner.calls] == ["shellcheck", "shfmt"]


def test_run_checks_runs_the_analyzer_for_a_powershell_repo(tmp_path) -> None:
    caller = _make_caller_repo(tmp_path, bash=True, powershell=True)
    runner = RecordingRunner()

    verify_shell.run_checks(runner=runner, root=caller, which=_always_found)

    assert [call[0] for call in runner.calls] == ["shellcheck", "shfmt", "pwsh"]


def test_analyzer_is_invoked_with_the_distributed_helper(tmp_path) -> None:
    caller = _make_caller_repo(tmp_path, powershell=True)
    runner = RecordingRunner()

    verify_shell.run_checks(runner=runner, root=caller, which=_always_found)

    # ヘルパー自身も bin/*.ps1 に入る．配布物を検査から外さない
    assert runner.calls == [
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(caller / "bin" / "analyze-powershell.ps1"),
            "bin/analyze-powershell.ps1",
            "bin/example.ps1",
        ]
    ]


def test_missing_analyzer_is_named_before_pwsh_runs(tmp_path) -> None:
    """雛形だけコピーして analyze-powershell.ps1 を置き忘れた caller を助ける．

    そのまま pwsh へ渡すと「ファイルが無い」という pwsh 側の失敗になり，
    何を置き忘れたのかが読み取れない．
    """
    caller = _make_caller_repo(tmp_path, powershell=True)
    (caller / "bin" / "analyze-powershell.ps1").unlink()
    runner = RecordingRunner()

    returncode = verify_shell.run_checks(
        runner=runner, root=caller, which=_always_found
    )

    assert returncode == 1
    assert runner.calls == []


def test_missing_analyzer_reports_the_expected_path(tmp_path, capsys) -> None:
    caller = _make_caller_repo(tmp_path, powershell=True)
    (caller / "bin" / "analyze-powershell.ps1").unlink()

    verify_shell.run_checks(
        runner=RecordingRunner(), root=caller, which=_always_found
    )

    assert verify_shell.ANALYZER_RELATIVE_PATH in capsys.readouterr().err


def test_missing_analyzer_is_ignored_without_powershell_targets(tmp_path) -> None:
    """PowerShell 資産を持たない repo へ，置いていない helper を求めない．"""
    caller = _make_caller_repo(tmp_path, bash=True)
    runner = RecordingRunner()

    returncode = verify_shell.run_checks(
        runner=runner, root=caller, which=_always_found
    )

    assert returncode == 0
    assert [call[0] for call in runner.calls] == ["shellcheck", "shfmt"]


def test_run_shfmt_uses_the_configured_options() -> None:
    runner = RecordingRunner(returncode=1)

    returncode = verify_shell.run_shfmt(["bin/a.sh"], runner=runner)

    assert returncode == 1
    assert runner.calls == [
        ["shfmt", "-d", *verify_shell.SHFMT_OPTIONS, "bin/a.sh"]
    ]


# --- 失敗の集約と対象の可視化 ---


def test_run_checks_reports_every_failure(tmp_path) -> None:
    """途中で打ち切らない．1 回の実行で全ツールの指摘を出す．"""
    caller = _make_caller_repo(tmp_path, bash=True, powershell=True)
    runner = RecordingRunner(returncode=1)

    returncode = verify_shell.run_checks(
        runner=runner, root=caller, which=_always_found
    )

    assert returncode == 1
    assert len(runner.calls) == 3


def test_run_checks_prints_inspected_targets(tmp_path, capsys) -> None:
    caller = _make_caller_repo(tmp_path, bash=True, powershell=True)

    verify_shell.run_checks(
        runner=RecordingRunner(), root=caller, which=_always_found
    )

    captured = capsys.readouterr().out
    assert "bin/example.sh" in captured
    assert "bin/example.ps1" in captured


def test_missing_tool_is_reported_before_any_tool_runs(tmp_path) -> None:
    caller = _make_caller_repo(tmp_path, bash=True)
    runner = RecordingRunner()

    returncode = verify_shell.run_checks(
        runner=runner, root=caller, which=lambda _: None
    )

    assert returncode == 1
    assert runner.calls == []


def test_collect_targets_returns_sorted_repo_relative_paths(tmp_path) -> None:
    caller = _make_caller_repo(tmp_path, bash=True)

    targets = verify_shell.collect_targets(caller, verify_shell.BASH_PATTERNS)

    assert targets == ["bin/example.sh"]


# --- 配布物としての体裁 ---


def test_no_pep604_union_in_module_level_assignments() -> None:
    """caller が python-version を 3.9 まで下げても import できる状態を保つ．

    `from __future__ import annotations` が遅延するのは `:` 構文の注釈だけである．
    module level の代入は import 時に評価されるため，そこへ `X | None` を書くと
    3.9 以下で TypeError になる．型別名は `Optional[...]` で書く．
    """
    tree = ast.parse(TEMPLATE.read_text(encoding="utf-8"))

    offenders = [
        node.lineno
        for statement in tree.body
        if isinstance(statement, (ast.Assign, ast.AnnAssign))
        and statement.value is not None
        for node in ast.walk(statement.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
    ]

    assert offenders == []


def test_analyzer_template_is_saved_with_a_bom() -> None:
    """5.1 が cp932 として誤読しないよう UTF-8 BOM 付きで配る．"""
    assert ANALYZER_TEMPLATE.read_bytes().startswith(b"\xef\xbb\xbf")


def test_analyzer_template_uses_lf_line_endings() -> None:
    assert b"\r\n" not in ANALYZER_TEMPLATE.read_bytes()


def test_template_is_covered_by_the_repo_local_gate() -> None:
    """配布する .ps1 も中央の gate で検査する．配りっぱなしにしない．"""
    spec = importlib.util.spec_from_file_location(
        "central_verify_shell", REPO_ROOT / "bin" / "verify-shell.py"
    )
    central = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(central)

    targets = central.collect_targets(REPO_ROOT, central.POWERSHELL_PATTERNS)

    assert "templates/analyze-powershell.ps1" in targets
