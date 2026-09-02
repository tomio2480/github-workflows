# Pester のテストを実行する（verify-shell.py から呼ぶ）．
#
# 対象ファイルは呼び出し側が決める．本スクリプトは実行だけを担う．
# 失敗時は非 0 で終える．

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
  [string[]]$Path
)

$ErrorActionPreference = 'Stop'

Import-Module Pester -MinimumVersion 6.0.0

$configuration = New-PesterConfiguration
$configuration.Run.Path = $Path
$configuration.Run.Exit = $true
$configuration.Output.Verbosity = 'Normal'

Invoke-Pester -Configuration $configuration
