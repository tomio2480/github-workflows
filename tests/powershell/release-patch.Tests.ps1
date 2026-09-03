# bin/release-patch.ps1 の単体テスト（Pester）．
#
# 仕様は tests/bash/release-patch.bats と同じである．
# bash 版と PowerShell 版は同じ実行列・同じ終了コードを持つ約束のため，
# 移植の食い違いを検出できるよう同じ観点をなぞる．
#
# 実行は tests/powershell/release-patch-stub-runner.ps1 を子プロセスとして
# 起動する．対象スクリプトが exit を呼ぶため，同一プロセスでは検証できない．
#
# 引数不足やオプション値の欠落は PowerShell の parameter binder が拒む．
# 対象スクリプトの責務ではないため，bats にある該当ケースは持ち込まない．

BeforeAll {
  $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
  $script:Runner = Join-Path $PSScriptRoot 'release-patch-stub-runner.ps1'
  $script:Sha = '0123456789abcdef0123456789abcdef01234567'
  $script:RemoteMajorSha = '1111111111111111111111111111111111111111'

  function Invoke-Release {
    param(
      [hashtable]$Stub = @{},
      [string[]]$ScriptArgs
    )

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $log = Join-Path $tmp 'cmd.log'
    New-Item -ItemType File -Path $log | Out-Null

    $names = @(
      'STUB_LOG', 'STUB_TAG_EXISTS', 'STUB_TAG_SHA', 'STUB_COMMIT_MISSING',
      'STUB_SHALLOW', 'STUB_REMOTE_MAJOR_ABSENT', 'STUB_MAJOR_NOT_ANCESTOR',
      'STUB_RELEASE_EXISTS'
    )
    $saved = @{}
    foreach ($name in $names) {
      $saved[$name] = [Environment]::GetEnvironmentVariable($name)
      [Environment]::SetEnvironmentVariable($name, $null)
    }
    [Environment]::SetEnvironmentVariable('STUB_LOG', $log)
    foreach ($key in $Stub.Keys) {
      [Environment]::SetEnvironmentVariable($key, [string]$Stub[$key])
    }

    try {
      $output = & pwsh -NoProfile -File $script:Runner @ScriptArgs 2>&1
      $code = $LASTEXITCODE
    } finally {
      foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name])
      }
    }

    $commands = @()
    if (Test-Path -LiteralPath $log) {
      $commands = @(Get-Content -LiteralPath $log)
    }
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $tmp

    return [pscustomobject]@{
      ExitCode = $code
      Output   = ($output | Out-String)
      Commands = $commands
    }
  }

  function New-NotesFile {
    $path = Join-Path ([System.IO.Path]::GetTempPath()) (
      [System.Guid]::NewGuid().ToString() + '.md'
    )
    Set-Content -LiteralPath $path -Value 'release notes body'
    return $path
  }

  $script:NotesFile = New-NotesFile
}

AfterAll {
  Remove-Item -Force -ErrorAction SilentlyContinue $script:NotesFile
}

Describe '入力検証' {
  It 'vX.Y.Z 形式でなければ 1 で終える' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'version'
  }

  It 'SHA が 40 桁でなければ 1 で終える' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', 'abc1234', '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'SHA'
  }

  It 'notes ファイルが無ければ 1 で終える' {
    $missing = Join-Path ([System.IO.Path]::GetTempPath()) 'no-such-notes.md'

    $result = Invoke-Release -ScriptArgs @('v2.12.5', $script:Sha, '-NotesFile', $missing)

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'notes'
  }

  It '凍結中の v1 系を拒む' {
    $result = Invoke-Release -ScriptArgs @(
      'v1.2.3', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'v1'
    ($result.Commands -match '^git tag') | Should -BeNullOrEmpty
  }

  It 'ハイフン始まりのブランチ名を拒む' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile, '-DeleteBranch', '--all'
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'branch'
  }

  It '完全修飾 ref をブランチ名として拒む' {
    # refs/tags/... を渡すとタグを消しうる
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile,
      '-DeleteBranch', 'refs/tags/v2.12.5'
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'branch'
  }
}

Describe 'ガード' {
  It '既存タグが別 commit を指していたら 1 で終える' {
    $result = Invoke-Release -Stub @{ STUB_TAG_EXISTS = '1' } -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'v2\.12\.5'
  }

  It 'commit がローカルに無ければ 1 で終える' {
    $result = Invoke-Release -Stub @{ STUB_COMMIT_MISSING = '1' } -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'commit'
  }
}

Describe '実行列' {
  It '定例の順序どおりに発行する' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 0
    # ガード 2 件（rev-parse / cat-file）の後に定例コマンドが並ぶ
    $result.Commands[0] | Should -Be "git rev-parse -q --verify refs/tags/v2.12.5^{commit}"
    $result.Commands[1] | Should -Be "git cat-file -e $($script:Sha)^{commit}"
    $result.Commands[2] | Should -Be "git tag v2.12.5 $($script:Sha)"
    $result.Commands[3] | Should -Be 'git push origin v2.12.5'
    $result.Commands[4] | Should -Be 'gh release view v2.12.5'
    $result.Commands[5] | Should -Be (
      "gh release create v2.12.5 --title v2.12.5 --notes-file $($script:NotesFile)"
    )
    $result.Commands[6] | Should -Be 'git ls-remote origin refs/tags/v2'
    $result.Commands[7] | Should -Be 'git rev-parse --is-shallow-repository'
    $result.Commands[8] | Should -Be 'git fetch --quiet origin refs/tags/v2'
    $result.Commands[9] | Should -Be (
      "git merge-base --is-ancestor $($script:RemoteMajorSha) $($script:Sha)"
    )
    $result.Commands[10] | Should -Be 'git tag -f v2 v2.12.5'
    $result.Commands[11] | Should -Be (
      "git push --force-with-lease=refs/tags/v2:$($script:RemoteMajorSha) origin v2"
    )
    $result.Commands.Count | Should -Be 12
  }

  It 'shallow クローンでは祖先検査の前に深さを解消する' {
    $result = Invoke-Release -Stub @{ STUB_SHALLOW = '1' } -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 0
    $result.Commands | Should -Contain 'git fetch --quiet --unshallow origin refs/tags/v2'
    $result.Commands | Should -Not -Contain 'git fetch --quiet origin refs/tags/v2'
  }

  It 'release create へ --target を付けない' {
    # 既存タグへの --target は HTTP 422 で失敗する
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 0
    ($result.Commands -match '--target') | Should -BeNullOrEmpty
  }

  It '-Notes でインラインの本文を渡す' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-Notes', 'one-line note'
    )

    $result.ExitCode | Should -Be 0
    $result.Commands | Should -Contain (
      'gh release create v2.12.5 --title v2.12.5 --notes one-line note'
    )
  }

  It 'マージ済みブランチを refs/heads 明示の refspec で削除する' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile,
      '-DeleteBranch', 'feat/some-branch'
    )

    $result.ExitCode | Should -Be 0
    $result.Commands | Should -Contain 'git push origin --delete refs/heads/feat/some-branch'
  }
}

Describe '冪等な再実行' {
  It '既存タグが要求 SHA を指していれば作成だけ飛ばす' {
    $result = Invoke-Release -Stub @{
      STUB_TAG_EXISTS = '1'; STUB_TAG_SHA = $script:Sha
    } -ScriptArgs @('v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile)

    $result.ExitCode | Should -Be 0
    $result.Commands | Should -Not -Contain "git tag v2.12.5 $($script:Sha)"
    $result.Commands | Should -Contain 'git push origin v2.12.5'
    ($result.Commands -match '^gh release create v2\.12\.5') | Should -Not -BeNullOrEmpty
  }

  It 'Release が既に在れば作成を飛ばす' {
    $result = Invoke-Release -Stub @{ STUB_RELEASE_EXISTS = '1' } -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 0
    ($result.Commands -match '^gh release create') | Should -BeNullOrEmpty
    $result.Commands | Should -Contain 'git tag -f v2 v2.12.5'
  }

  It 'Release 未作成でも gh の stderr で中断しない' {
    # gh は未作成時に stderr へ書いて非 0 で終える．想定内の分岐である
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile, '-DryRun'
    )

    $result.ExitCode | Should -Be 0
    $result.Output | Should -Match 'dry-run: no changes were made'
  }
}

Describe 'major mutable タグの保護' {
  It 'remote が祖先でなければ major へ触れず 1 で終える' {
    $result = Invoke-Release -Stub @{ STUB_MAJOR_NOT_ANCESTOR = '1' } -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'rewind'
    ($result.Commands -match '^git tag -f v2') | Should -BeNullOrEmpty
    ($result.Commands -match 'origin v2$') | Should -BeNullOrEmpty
  }

  It 'remote にタグが無ければ lease 無しで push する' {
    $result = Invoke-Release -Stub @{ STUB_REMOTE_MAJOR_ABSENT = '1' } -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 0
    $result.Commands | Should -Contain 'git push origin v2'
    ($result.Commands -match '--force-with-lease') | Should -BeNullOrEmpty
  }

  It 'major mutable タグをバージョンから導く' {
    $result = Invoke-Release -ScriptArgs @(
      'v3.0.1', $script:Sha, '-NotesFile', $script:NotesFile
    )

    $result.ExitCode | Should -Be 0
    $result.Commands | Should -Contain 'git tag -f v3 v3.0.1'
    $result.Commands | Should -Contain (
      "git push --force-with-lease=refs/tags/v3:$($script:RemoteMajorSha) origin v3"
    )
  }
}

Describe 'dry-run' {
  It 'コマンドを示すだけで変更を加えない' {
    $result = Invoke-Release -ScriptArgs @(
      'v2.12.5', $script:Sha, '-NotesFile', $script:NotesFile, '-DryRun'
    )

    $result.ExitCode | Should -Be 0
    $result.Output | Should -Match 'git push origin v2\.12\.5'
    # ガード（読み取り専用）以外は実行されない
    ($result.Commands -match '^git tag') | Should -BeNullOrEmpty
    ($result.Commands -match '^git push') | Should -BeNullOrEmpty
    ($result.Commands -match '^gh release create') | Should -BeNullOrEmpty
    # fetch はローカルへ書き込むため dry-run では行わない
    ($result.Commands -match '^git fetch') | Should -BeNullOrEmpty
  }
}
