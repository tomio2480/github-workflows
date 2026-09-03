# bin/lib/native.ps1 の単体テスト（Pester）．
#
# 対象は Invoke-NativeCommand ただ 1 つである．
# 終了コードで分岐する native command 呼び出しを，stderr や非 0 終了で
# 終了エラーへ昇格させずに実行することを担保する（Issue #179）．

BeforeAll {
  $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
  $script:Helper = Join-Path $script:RepoRoot 'bin/lib/native.ps1'
  $script:Probe = Join-Path $PSScriptRoot 'native-probe.ps1'
  . $script:Helper
}

Describe 'Invoke-NativeCommand' {
  It 'scriptblock の標準出力をそのまま返す' {
    Invoke-NativeCommand { 'hello' } | Should -Be 'hello'
  }

  It '-ArgumentList を scriptblock の $args へ渡す' {
    Invoke-NativeCommand { $args -join ',' } -ArgumentList @('a', 'b') |
      Should -Be 'a,b'
  }

  It '終了コードを呼び出し元へ残す' {
    Invoke-NativeCommand { $global:LASTEXITCODE = 7 }

    $LASTEXITCODE | Should -Be 7
  }

  It 'scriptblock の内側では停止設定を緩める' {
    # 昇格の抑止はこの緩和に依る．5.1 を持たない環境でも機構を検査できる
    $ErrorActionPreference = 'Stop'

    Invoke-NativeCommand { $ErrorActionPreference } | Should -Not -Be 'Stop'
  }

  It '呼び出し元の停止設定を書き換えない' {
    # 緩和が漏れると，以降の Write-Error が止まらなくなる
    $ErrorActionPreference = 'Stop'

    Invoke-NativeCommand { 'x' } | Out-Null

    $ErrorActionPreference | Should -Be 'Stop'
  }

  It 'stderr を出す native command で落ちない' -Skip:(
    $null -eq (Get-Command powershell.exe -ErrorAction SilentlyContinue)
  ) {
    # 昇格は Windows PowerShell 5.1 でのみ起きる．関数スタブでは native
    # command にならず再現できないため，実体の 5.1 を子プロセスで起動する
    $output = & powershell.exe -NoProfile -ExecutionPolicy Bypass `
      -File $script:Probe -Helper $script:Helper 2>&1
    $code = $LASTEXITCODE

    $code | Should -Be 0
    ($output | Out-String) | Should -Match 'lastexit=1'
  }
}
