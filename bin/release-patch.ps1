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

# 終了コードで分岐する native command は Invoke-NativeCommand 経由で呼ぶ．
# 直接呼ぶと Windows PowerShell 5.1 で stderr が終了エラーへ昇格する（Issue #179）
. (Join-Path $PSScriptRoot 'lib/native.ps1')

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
$ExistingTagSha = Invoke-NativeCommand {
  git rev-parse -q --verify "refs/tags/${Version}^{commit}" 2> $null
}
if ($LASTEXITCODE -eq 0 -and $ExistingTagSha) {
  if ($ExistingTagSha -eq $MergeSha) {
    Write-Output "note: tag ${Version} already points at the requested commit; resuming"
    $ResumeTag = $true
  } else {
    Write-Error "tag ${Version} already exists at a different commit: ${ExistingTagSha}"
    exit 1
  }
}

Invoke-NativeCommand { git cat-file -e "${MergeSha}^{commit}" 2> $null }
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
  # 失敗は下の 1 箇所で報告する．昇格させると，この文言が出ないまま落ちる
  Invoke-NativeCommand { & $CommandLine[0] @($CommandLine[1..($CommandLine.Count - 1)]) }
  if ($LASTEXITCODE -ne 0) {
    Write-Error "command failed: $($CommandLine -join ' ')"
    exit 1
  }
}

if (-not $ResumeTag) {
  Invoke-Step @('git', 'tag', $Version, $MergeSha)
}
Invoke-Step @('git', 'push', 'origin', $Version)

# 再実行時に作成済み Release で失敗しないよう存在確認する（読み取り専用）．
# 未作成なら gh は stderr へ書いて非 0 で終える．想定内の分岐である
Invoke-NativeCommand { gh release view $Version *> $null }
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
# 出力なしには「タグが無い」と「照会が失敗した」の 2 つがある．
# 区別しないと，認証切れが lease 無し push へ化ける
$RemoteMajorLine = Invoke-NativeCommand { git ls-remote origin "refs/tags/${Major}" }
if ($LASTEXITCODE -ne 0) {
  Write-Error "could not read refs/tags/${Major} from origin"
  exit 1
}
$RemoteMajorSha = if ($RemoteMajorLine) { ($RemoteMajorLine -split "`t")[0] } else { '' }
if ($RemoteMajorSha -ne '') {
  # dry-run では fetch しない（FETCH_HEAD・object db への書き込みを避ける）．
  # commit がローカルに無く検査できない場合は，本実行時に検査される旨を示す．
  # 本実行では fetch で必ず引くため，この確認自体を行わない（bash 版と同じ）
  $DeferCheck = $false
  if ($DryRun) {
    Invoke-NativeCommand { git cat-file -e "${RemoteMajorSha}^{commit}" 2> $null }
    $DeferCheck = ($LASTEXITCODE -ne 0)
  }
  if ($DeferCheck) {
    Write-Output "[dry-run] (monotonicity check for ${Major} deferred to a real run)"
  } else {
    if (-not $DryRun) {
      # shallow クローンでは remote タグと新 patch の間の履歴が欠けており，
      # 祖先関係を判定できない（実際は祖先でも非祖先と誤判定される）．
      # そのため深さを解消してから fetch する．
      #
      # 失敗は自分で検査する．後段の merge-base には委ねられない．
      # remote sha がすでにローカルにあれば，fetch が落ちても merge-base は
      # 成功しうる．そのとき「履歴を取り損ねたまま祖先と判定した」に化ける
      $Shallow = Invoke-NativeCommand { git rev-parse --is-shallow-repository }
      if ($LASTEXITCODE -ne 0) {
        Write-Error 'failed to determine whether the repository is shallow'
        exit 1
      }

      if ($Shallow -eq 'true') {
        Invoke-NativeCommand { git fetch --quiet --unshallow origin "refs/tags/${Major}" }
      } else {
        Invoke-NativeCommand { git fetch --quiet origin "refs/tags/${Major}" }
      }
      if ($LASTEXITCODE -ne 0) {
        Write-Error "failed to fetch refs/tags/${Major} from origin"
        exit 1
      }
    }
    Invoke-NativeCommand { git merge-base --is-ancestor $RemoteMajorSha $MergeSha }
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
