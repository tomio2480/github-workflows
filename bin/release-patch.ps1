# PR マージ後の定例 patch リリースを 1 コマンドで実行する（PowerShell 版）．
#
# 実行列は bin/release-patch.sh と同一（同スクリプトのヘッダーコメントを参照）．
# 版番号の決定（最新タグ確認・patch/minor 判断）はスクリプト外の責務とする．

[CmdletBinding(DefaultParameterSetName = 'NotesFile')]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$Version,

  [Parameter(Mandatory = $true, Position = 1)]
  [string]$MergeSha,

  [Parameter(Mandatory = $true, ParameterSetName = 'NotesText')]
  [string]$Notes,

  [Parameter(Mandatory = $true, ParameterSetName = 'NotesFile')]
  [string]$NotesFile,

  [string]$DeleteBranch = '',

  [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# --- 入力検証（意味的に具体的 → 汎用的の順） ---

if ($Version -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$') {
  Write-Error "version must match vX.Y.Z: ${Version}"
  exit 1
}

if ($MergeSha -notmatch '^[0-9a-f]{40}$') {
  Write-Error "merge-sha must be a full 40-hex SHA: ${MergeSha}"
  exit 1
}

if ($PSCmdlet.ParameterSetName -eq 'NotesFile' -and -not (Test-Path $NotesFile -PathType Leaf)) {
  Write-Error "notes file not found: ${NotesFile}"
  exit 1
}

# ハイフン始まりはオプション誤解釈（例: --all）を招くため拒否する
if ($DeleteBranch -ne '' -and $DeleteBranch.StartsWith('-')) {
  Write-Error "invalid branch name: ${DeleteBranch}"
  exit 1
}

$Major = $Version.Split('.')[0]

# --- ガード（読み取り専用のため dry-run でも実行する） ---

git rev-parse -q --verify "refs/tags/${Version}" *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Error "tag already exists: ${Version}"
  exit 1
}

git cat-file -e "${MergeSha}^{commit}" 2> $null
if ($LASTEXITCODE -ne 0) {
  Write-Error "commit not found in local repository: ${MergeSha}"
  exit 1
}

# --- 実行 ---

function Invoke-Step {
  param([string[]]$CommandLine)
  if ($DryRun) {
    Write-Output "[dry-run] $($CommandLine -join ' ')"
    return
  }
  Write-Output "+ $($CommandLine -join ' ')"
  & $CommandLine[0] @($CommandLine[1..($CommandLine.Count - 1)])
  if ($LASTEXITCODE -ne 0) {
    Write-Error "command failed: $($CommandLine -join ' ')"
    exit 1
  }
}

Invoke-Step @('git', 'tag', $Version, $MergeSha)
Invoke-Step @('git', 'push', 'origin', $Version)

if ($PSCmdlet.ParameterSetName -eq 'NotesFile') {
  Invoke-Step @('gh', 'release', 'create', $Version, '--title', $Version, '--notes-file', $NotesFile)
} else {
  Invoke-Step @('gh', 'release', 'create', $Version, '--title', $Version, '--notes', $Notes)
}

Invoke-Step @('git', 'tag', '-f', $Major, $Version)
Invoke-Step @('git', 'push', '-f', 'origin', $Major)

if ($DeleteBranch -ne '') {
  Invoke-Step @('git', 'push', 'origin', '--delete', $DeleteBranch)
}

if ($DryRun) {
  Write-Output 'dry-run: no changes were made'
} else {
  Write-Output "released ${Version} and moved ${Major}"
}
