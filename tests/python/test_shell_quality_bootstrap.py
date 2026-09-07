"""PowerShell module の導入 step が Issue #205 の故障へ戻らないことを検査する．

`Set-PSRepository` は PSGallery が登録済みであることを前提とする．未登録の
runner に当たると toolchain setup の段階で落ち，検査対象へ到達する前に
中央の reusable workflow が全 caller で赤くなる．

同じ step は `verify` と `verify-windows` の 2 箇所にある．片方だけ直すと
もう片方が残るため，件数も併せて検査する．
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "shell-quality.yml"
)

STEP_NAME = "Install PowerShell analyzers and tests"

# `verify` と `verify-windows` の 2 job にある．
EXPECTED_JOBS = ("verify", "verify-windows")

# 固定している版．導入時と導入後の突き合わせで同じ値を使う．
PINNED_VERSIONS = ("1.25.0", "6.1.0")


def _bootstrap_runs() -> dict[str, str]:
    """`job 名 -> run の中身` を導入 step の分だけ返す．"""
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for job_name, job in document["jobs"].items():
        for step in job.get("steps", []):
            if step.get("name") == STEP_NAME:
                found[job_name] = step["run"]
    return found


def _code_only(run: str) -> str:
    """コメント行を落とす．

    検査対象は実行される行である．コメントへ書いた禁止語で落ちると，
    経緯を書けなくなる．
    """
    lines = [
        line for line in run.splitlines() if not line.lstrip().startswith("#")
    ]
    return "\n".join(lines)


def test_bootstrap_steps_are_found() -> None:
    """走査が空振りしていないこと．

    step 名を変えると，以降の検査が 0 件を検査して素通りする．
    """
    runs = _bootstrap_runs()

    assert sorted(runs) == sorted(EXPECTED_JOBS), (
        f"'{STEP_NAME}' の step を {EXPECTED_JOBS} の各 job で見つけられなかった"
        f"（実際は {sorted(runs)}）．step 名か job 構成が変わった可能性がある．"
    )


@pytest.mark.parametrize("job_name", EXPECTED_JOBS)
def test_bootstrap_does_not_assume_registered_gallery(job_name: str) -> None:
    """`Set-PSRepository` へ戻らないこと（Issue #205）．

    信頼確認は `Install-Module -Force` が抑える．実測では PSGallery が
    登録済み・Untrusted の状態でも `-Force` 単独で導入できた．
    """
    run = _code_only(_bootstrap_runs()[job_name])

    assert "Set-PSRepository" not in run, (
        f"job {job_name}: `Set-PSRepository` は PSGallery の登録を前提とする．"
        "未登録の runner で落ちるため使わない（Issue #205）．"
    )


@pytest.mark.parametrize("job_name", EXPECTED_JOBS)
def test_bootstrap_registers_gallery_when_missing(job_name: str) -> None:
    """未登録なら登録すること．

    `Install-Module -Force` 単独では埋まらない．実測では未登録状態の
    ubuntu・windows の双方で落ちた．
    """
    run = _code_only(_bootstrap_runs()[job_name])

    assert "Get-PSRepository -Name PSGallery" in run, (
        f"job {job_name}: PSGallery の登録有無を確かめていない．"
    )
    assert "Register-PSRepository -Default" in run, (
        f"job {job_name}: 未登録の runner で PSGallery を登録していない．"
    )


@pytest.mark.parametrize("job_name", EXPECTED_JOBS)
def test_bootstrap_asserts_installed_versions(job_name: str) -> None:
    """導入できたことを版まで突き合わせること．

    pwsh 7 は native command の非 0 終了で停止しない（`docs/shell-quality.md`）．
    `Install-Module` の内側が native command を呼んで黙って失敗した場合，
    PowerShell のエラーは飛ばない．**「エラーが飛ばなかった」を成功の根拠に
    すると，導入できていない状態を成功と読む．**

    後段の `$LASTEXITCODE` の戻しが，その痕跡まで消してしまう．
    消極的な根拠ではなく，意図した版が実際に入ったことを確かめる．
    """
    run = _code_only(_bootstrap_runs()[job_name])

    assert "Get-Module -ListAvailable" in run, (
        f"job {job_name}: 導入後に module の在否を確かめていない．"
    )
    assert "throw" in run, (
        f"job {job_name}: 導入できていないときに step を落としていない．"
    )
    for version in PINNED_VERSIONS:
        assert run.count(version) >= 2, (
            f"job {job_name}: {version} を導入時にしか使っていない．"
            "導入後の突き合わせでも同じ版を名指しすること．"
        )


@pytest.mark.parametrize("job_name", EXPECTED_JOBS)
def test_version_assertion_precedes_exit_code_reset(job_name: str) -> None:
    """版の突き合わせを `$LASTEXITCODE` の戻しより前に置くこと．

    戻しが先だと，導入の失敗を消してから確かめることになる．
    """
    run = _code_only(_bootstrap_runs()[job_name])

    assert run.index("throw") < run.index("$global:LASTEXITCODE = 0"), (
        f"job {job_name}: 版の突き合わせが `$LASTEXITCODE` の戻しより後にある．"
    )


@pytest.mark.parametrize("job_name", EXPECTED_JOBS)
def test_bootstrap_resets_last_exit_code(job_name: str) -> None:
    """`$LASTEXITCODE` を登録より後で戻すこと．

    `Register-PSRepository -Default` は windows runner で内部の `nuget.exe`
    が異常終了し `$LASTEXITCODE` へ 1 を残す．登録は成功しているのに step が
    落ちるため，成功を失敗と誤認する．
    """
    run = _code_only(_bootstrap_runs()[job_name])

    assert "$global:LASTEXITCODE = 0" in run, (
        f"job {job_name}: `$LASTEXITCODE` を戻していない．"
        "`Register-PSRepository` の残す 1 が step の終了コードへ伝播する．"
    )

    register_at = run.index("Register-PSRepository -Default")
    reset_at = run.index("$global:LASTEXITCODE = 0")
    assert reset_at > register_at, (
        f"job {job_name}: `$LASTEXITCODE` の戻しが登録より前にある．"
        "登録が残す値を消せない．"
    )
