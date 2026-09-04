# bin/check-native-calls.ps1 の fixture．規律を守った形である．

. (Join-Path $PSScriptRoot '../../../bin/lib/native.ps1')

$Line = Invoke-NativeCommand { git ls-remote origin 'refs/heads/main' }
if ($LASTEXITCODE -ne 0) {
  Write-Error 'failed'
  exit 1
}

Invoke-NativeCommand {
  gh release view v1.0.0 *> $null
}
if ($LASTEXITCODE -eq 0) {
  Write-Output "exists: ${Line}"
}
