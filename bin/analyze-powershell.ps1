# PowerShell スクリプトを PSScriptAnalyzer で検査する．
#
# 使い方:
#   pwsh -NoProfile -File bin/analyze-powershell.ps1 <path> [<path> ...]
#
# 検査対象の決定は bin/verify-shell.py の責務とする．本スクリプトは受け取った
# path をそのまま検査し，Error または Warning が 1 件でもあれば非 0 で終わる．

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
