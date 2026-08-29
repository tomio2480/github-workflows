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

# 既存タグが要求 SHA を指す場合は途中失敗からの再開とみなし，
# タグ作成だけスキップして残りの手順を続行する（冪等な再実行）．
$ResumeTag = $false
$ExistingTagSha = git rev-parse -q --verify "refs/tags/${Version}^{commit}" 2> $null
if ($LASTEXITCODE -eq 0 -and $ExistingTagSha) {
  if ($ExistingTagSha -eq $MergeSha) {
    Write-Output "note: tag ${Version} already points at the requested commit; resuming"
    $ResumeTag = $true
  } else {
    Write-Error "tag ${Version} already exists at a different commit: ${ExistingTagSha}"
    exit 1
  }
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

if (-not $ResumeTag) {
  Invoke-Step @('git', 'tag', $Version, $MergeSha)
}
Invoke-Step @('git', 'push', 'origin', $Version)

# 再実行時に作成済み Release で失敗しないよう存在確認する（読み取り専用）
gh release view $Version *> $null
if ($LASTEXITCODE -eq 0) {
  Write-Output "note: release ${Version} already exists; skipping create"
} elseif ($PSCmdlet.ParameterSetName -eq 'NotesFile') {
  Invoke-Step @('gh', 'release', 'create', $Version, '--title', $Version, '--notes-file', $NotesFile)
} else {
  Invoke-Step @('gh', 'release', 'create', $Version, '--title', $Version, '--notes', $Notes)
}

Invoke-Step @('git', 'tag', '-f', $Major, $Version)

# 並行実行時に古いリリースが major mutable を巻き戻さないよう，
# push 直前の remote 値を lease に指定する（値が動いていれば push は失敗する）
$RemoteMajorLine = git ls-remote origin "refs/tags/${Major}"
$RemoteMajorSha = if ($RemoteMajorLine) { ($RemoteMajorLine -split "`t")[0] } else { '' }
if ($RemoteMajorSha -ne '') {
  Invoke-Step @('git', 'push', "--force-with-lease=refs/tags/${Major}:${RemoteMajorSha}", 'origin', $Major)
} else {
  Invoke-Step @('git', 'push', 'origin', $Major)
}

if ($DeleteBranch -ne '') {
  Invoke-Step @('git', 'push', 'origin', '--delete', $DeleteBranch)
}

if ($DryRun) {
  Write-Output 'dry-run: no changes were made'
} else {
  Write-Output "released ${Version} and moved ${Major}"
}
