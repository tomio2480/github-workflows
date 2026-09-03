# Invoke-NativeCommand の回帰確認に使う（tests/powershell/native.Tests.ps1 から起動）．
#
# Windows PowerShell 5.1 で $ErrorActionPreference = 'Stop' のまま
# stderr を出す native command を呼ぶと，終了エラーへ昇格して落ちる．
# ヘルパー経由なら最後まで進み，lastexit= 行を出せる．

param([Parameter(Mandatory = $true)][string]$Helper)

$ErrorActionPreference = 'Stop'

. $Helper

Invoke-NativeCommand { cmd /c "echo release not found 1>&2 & exit 1" } *> $null

Write-Output "lastexit=${LASTEXITCODE}"
exit 0
