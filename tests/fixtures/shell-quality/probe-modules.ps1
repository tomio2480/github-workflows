$ErrorActionPreference = "Stop"

$Analyzer = Get-Module PSScriptAnalyzer -ListAvailable |
    Where-Object Version -EQ ([version]"1.25.0") |
    Select-Object -First 1
$Pester = Get-Module Pester -ListAvailable |
    Where-Object Version -EQ ([version]"6.1.0") |
    Select-Object -First 1

if ($null -eq $Analyzer) {
    throw "PSScriptAnalyzer 1.25.0 is unavailable"
}
if ($null -eq $Pester) {
    throw "Pester 6.1.0 is unavailable"
}

Write-Output "PowerShell modules are available"
