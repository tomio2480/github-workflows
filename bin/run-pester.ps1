# Pester のテストを実行する（verify-shell.py から呼ぶ）．
#
# 対象ファイルは呼び出し側が決める．本スクリプトは実行だけを担う．
# 失敗時は非 0 で終える．
#
# -FailOnSkipped は skip も失敗として扱う．windows job から使う．
# Windows PowerShell 5.1 を要するテストは，5.1 が無ければ自ら skip する．
# skip を許したままでは，5.1 のために設けた job が何も検査せず緑で終わる
# （Issue #184）．

[CmdletBinding()]
param(
  [Parameter()]
  [switch]$FailOnSkipped,

  [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
  [string[]]$Path
)

$ErrorActionPreference = 'Stop'

Import-Module Pester -MinimumVersion 6.0.0

$configuration = New-PesterConfiguration
$configuration.Run.Path = $Path
# 終了コードは skip の判定後に自分で決める．Run.Exit はその前に抜けてしまう
$configuration.Run.PassThru = $true
$configuration.Output.Verbosity = 'Normal'

$result = Invoke-Pester -Configuration $configuration

if ($result.FailedCount -gt 0) {
  exit 1
}

if ($FailOnSkipped -and $result.SkippedCount -gt 0) {
  Write-Error "skipped $($result.SkippedCount) test(s) while -FailOnSkipped is set"
  exit 1
}

exit 0
