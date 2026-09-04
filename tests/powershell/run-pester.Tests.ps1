# bin/run-pester.ps1 の単体テスト（Pester）．
#
# 対象は終了コードの伝え方と -FailOnSkipped の振る舞いである．
# 入れ子の Invoke-Pester を避けるため，実体を子プロセスとして起動する．
#
# skip を失敗として扱う経路は windows job のためにある．
# 5.1 の不在でテストが飛んでも job が緑で終わる状態を止める（Issue #184）．

BeforeAll {
  $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
  $script:Runner = Join-Path $script:RepoRoot 'bin/run-pester.ps1'
  $script:FixtureDir = Join-Path $PSScriptRoot 'fixtures'

  function Invoke-Runner {
    param(
      [string]$Fixture,
      [switch]$FailOnSkipped
    )

    $target = Join-Path $script:FixtureDir $Fixture
    $arguments = @('-NoProfile', '-File', $script:Runner)
    if ($FailOnSkipped) {
      $arguments += '-FailOnSkipped'
    }
    $arguments += $target

    $output = & pwsh @arguments 2>&1
    return [pscustomobject]@{
      ExitCode = $LASTEXITCODE
      Output   = ($output | Out-String)
    }
  }
}

Describe 'bin/run-pester.ps1' {
  It '成功する suite で 0 を返す' {
    (Invoke-Runner -Fixture 'passing.Tests.ps1').ExitCode | Should -Be 0
  }

  It '失敗する suite で非 0 を返す' {
    (Invoke-Runner -Fixture 'failing.Tests.ps1').ExitCode | Should -Not -Be 0
  }

  It '既定では skip を許容する' {
    # ubuntu job は 5.1 を持たない．そこでの skip は想定内である
    (Invoke-Runner -Fixture 'skipped.Tests.ps1').ExitCode | Should -Be 0
  }

  It '-FailOnSkipped では skip を失敗にする' {
    $result = Invoke-Runner -Fixture 'skipped.Tests.ps1' -FailOnSkipped

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'skipped'
  }

  It '-FailOnSkipped でも成功する suite は 0 を返す' {
    (Invoke-Runner -Fixture 'passing.Tests.ps1' -FailOnSkipped).ExitCode |
      Should -Be 0
  }
}
