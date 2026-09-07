# PowerShell スクリプトを PSScriptAnalyzer で検査する（caller 向け雛形）．
#
# 使い方:
#   pwsh -NoProfile -File bin/analyze-powershell.ps1 <path> [<path> ...]
#
# 検査対象の決定は bin/verify-shell.py の責務とする．本スクリプトは受け取った
# path をそのまま検査し，Error または Warning が 1 件でもあれば非 0 で終わる．
#
# 除外したい規則がある repo は PSScriptAnalyzerSettings.psd1 を置き，
# Invoke-ScriptAnalyzer へ -Settings で渡す．
# 本ファイルは UTF-8 BOM 付き・LF で保存する．
# BOM が無いと Windows PowerShell 5.1 が cp932 として誤読する．

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
  [string[]]$Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Import-Module PSScriptAnalyzer

$findings = @()
foreach ($target in $Path) {
  $findings += Invoke-ScriptAnalyzer -Path $target -Severity Error, Warning
}

if ($findings.Count -gt 0) {
  $findings |
    Format-Table -AutoSize RuleName, Severity, ScriptName, Line, Message |
    Out-String -Width 200 |
    Write-Output
  exit 1
}

Write-Output "PSScriptAnalyzer: no findings in $($Path.Count) file(s)"
exit 0
