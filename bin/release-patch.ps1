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

# v1 系は self-detection bug により凍結中（動かさない不変条件）．
# 根拠は CLAUDE.md・docs/security.md・docs/fork-usage.md を参照
if ($Version -like 'v1.*') {
  Write-Error "the v1 series is frozen and must not move: ${Version}"
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

# ハイフン始まりはオプション誤解釈（例: --all）を招くため拒否する．
# refs/ 始まりは refs/heads/ を前置する削除 refspec と二重になるため拒否する
# （refs/tags/... 誤指定によるタグ削除の防止を兼ねる）
if ($DeleteBranch -ne '' -and ($DeleteBranch.StartsWith('-') -or $DeleteBranch.StartsWith('refs/'))) {
  Write-Error "invalid branch name (short name expected): ${DeleteBranch}"
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

# 並行実行時に古いリリースが major mutable を巻き戻さないよう，二段で守る．
# 1) 単調性検査: remote の現在値が新 patch commit の祖先であることを確認する．
#    lease は「観測値からの変化」しか検知せず，版の順序は保証しないため必要．
# 2) lease: 検査済みの観測値を期待値に指定し，push までの間の移動を検知する．
$RemoteMajorLine = git ls-remote origin "refs/tags/${Major}"
$RemoteMajorSha = if ($RemoteMajorLine) { ($RemoteMajorLine -split "`t")[0] } else { '' }
if ($RemoteMajorSha -ne '') {
  # dry-run では fetch しない（FETCH_HEAD・object db への書き込みを避ける）．
  # commit がローカルに無く検査できない場合は，本実行時に検査される旨を示す
  git cat-file -e "${RemoteMajorSha}^{commit}" 2> $null
  $RemoteCommitIsLocal = ($LASTEXITCODE -eq 0)
  if ($DryRun -and -not $RemoteCommitIsLocal) {
    Write-Output "[dry-run] (monotonicity check for ${Major} deferred to a real run)"
  } else {
    if (-not $DryRun) {
      git fetch --quiet origin "refs/tags/${Major}"
    }
    git merge-base --is-ancestor $RemoteMajorSha $MergeSha
    if ($LASTEXITCODE -ne 0) {
      Write-Error "remote ${Major} (${RemoteMajorSha}) is ahead of ${MergeSha}; refusing to rewind"
      exit 1
    }
  }
}

Invoke-Step @('git', 'tag', '-f', $Major, $Version)

if ($RemoteMajorSha -ne '') {
  Invoke-Step @('git', 'push', "--force-with-lease=refs/tags/${Major}:${RemoteMajorSha}", 'origin', $Major)
} else {
  Invoke-Step @('git', 'push', 'origin', $Major)
}

if ($DeleteBranch -ne '') {
  # refspec を refs/heads/ 明示で組み，タグ等の別種 ref を誤削除しない
  Invoke-Step @('git', 'push', 'origin', '--delete', "refs/heads/${DeleteBranch}")
}

if ($DryRun) {
  Write-Output 'dry-run: no changes were made'
} else {
  Write-Output "released ${Version} and moved ${Major}"
}
