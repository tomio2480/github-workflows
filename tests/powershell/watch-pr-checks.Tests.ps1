# bin/watch-pr-checks.ps1 の単体テスト（Pester）．
#
# 仕様は tests/bash/watch-pr-checks.bats と同じである．
# bash 版と PowerShell 版は同じ実行列・同じ終了コードを持つ約束のため，
# 移植の食い違いを検出できるよう同じ観点をなぞる．
#
# 実行は tests/powershell/stub-runner.ps1 を子プロセスとして起動する．
# 対象スクリプトが exit を呼ぶため，同一プロセスでは検証できない．

BeforeAll {
  $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
  $script:Runner = Join-Path $PSScriptRoot 'stub-runner.ps1'
  $script:RemoteSha = '1111111111111111111111111111111111111111'
  $script:StaleSha = '2222222222222222222222222222222222222222'

  function Invoke-Watch {
    param(
      [hashtable]$Stub = @{},
      [string[]]$ScriptArgs
    )

    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $log = Join-Path $tmp 'cmd.log'
    New-Item -ItemType File -Path $log | Out-Null

    $names = @(
      'STUB_LOG', 'STUB_STATE_DIR', 'STUB_REMOTE_EMPTY', 'STUB_GH_LAG',
      'STUB_CHECKS_LAG', 'STUB_CHECKS', 'STUB_HEAD_MOVES'
    )
    $saved = @{}
    foreach ($name in $names) {
      $saved[$name] = [Environment]::GetEnvironmentVariable($name)
      [Environment]::SetEnvironmentVariable($name, $null)
    }
    [Environment]::SetEnvironmentVariable('STUB_LOG', $log)
    [Environment]::SetEnvironmentVariable('STUB_STATE_DIR', $tmp)
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
}

Describe '入力検証' {
  It 'PR 番号が数値でなければ 1 で終える' {
    $result = Invoke-Watch -ScriptArgs @('-Pr', 'abc')

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'pr-number'
  }

  It '-ExpectSha が 40 桁でなければ 1 で終える' {
    $result = Invoke-Watch -ScriptArgs @('-Pr', '165', '-ExpectSha', 'abc1234')

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'ExpectSha'
  }
}

Describe 'remote の実体を正とする' {
  It 'ブランチが remote に無ければ checks を照会せず 1 で終える' {
    $result = Invoke-Watch -Stub @{ STUB_REMOTE_EMPTY = '1' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '0'
    )

    $result.ExitCode | Should -Be 1
    $result.Output | Should -Match 'origin'
    ($result.Commands -match 'gh pr checks') | Should -BeNullOrEmpty
  }

  It '-ExpectSha を渡すと remote へ問い合わせない' {
    $result = Invoke-Watch -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30',
      '-ExpectSha', $script:RemoteSha
    )

    $result.ExitCode | Should -Be 0
    ($result.Commands -match '^git ls-remote') | Should -BeNullOrEmpty
  }
}

Describe 'gh がリモートへ追いつくまで待つ' {
  It '追いつくまで headRefOid を引き直す' {
    $result = Invoke-Watch -Stub @{ STUB_GH_LAG = '2' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 0
    @($result.Commands -match 'headRefOid').Count | Should -BeGreaterOrEqual 3
  }

  It '追いつかないまま締切に達したら checks を照会せず 2 で終える' {
    $result = Invoke-Watch -Stub @{ STUB_GH_LAG = '99' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '0'
    )

    $result.ExitCode | Should -Be 2
    $result.Output | Should -Match $script:RemoteSha
    ($result.Commands -match 'gh pr checks') | Should -BeNullOrEmpty
  }
}

Describe 'checks が出そろうまで待つ' {
  It '登録されるまで照会を繰り返す' {
    $result = Invoke-Watch -Stub @{ STUB_CHECKS_LAG = '2' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 0
    @($result.Commands -match 'gh pr checks').Count | Should -BeGreaterOrEqual 3
  }

  It '1 件も登録されないまま締切に達したら 2 で終える' {
    $result = Invoke-Watch -Stub @{ STUB_CHECKS_LAG = '99' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '0'
    )

    $result.ExitCode | Should -Be 2
  }

  It 'pending がある間は待ち続ける' {
    $result = Invoke-Watch -Stub @{ STUB_CHECKS = 'pending' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 0
    @($result.Commands -match 'gh pr checks').Count | Should -BeGreaterOrEqual 3
  }

  It '件数が増えなくなるまで待つ' {
    $result = Invoke-Watch -Stub @{ STUB_CHECKS = 'late' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 0
    $result.Output | Should -Match 'all 2 checks passed'
  }

  It '件数が増え続ける場合は締切で 2 で終える' {
    $result = Invoke-Watch -Stub @{ STUB_CHECKS = 'growing' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '0'
    )

    $result.ExitCode | Should -Be 2
    $result.Output | Should -Match $script:RemoteSha
  }
}

Describe '判定' {
  It '成功時は検査した commit を報告する' {
    $result = Invoke-Watch -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 0
    $result.Output | Should -Match $script:RemoteSha
  }

  It 'checks が失敗したら 3 で終える' {
    $result = Invoke-Watch -Stub @{ STUB_CHECKS = 'fail' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 3
    $result.Output | Should -Match $script:RemoteSha
  }

  It '監視中に head が動いたら 2 で終える' {
    $result = Invoke-Watch -Stub @{ STUB_HEAD_MOVES = '1' } -ScriptArgs @(
      '-Pr', '165', '-IntervalSeconds', '0', '-TimeoutSeconds', '30'
    )

    $result.ExitCode | Should -Be 2
    $result.Output | Should -Match $script:StaleSha
  }
}
