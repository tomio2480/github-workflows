# PR の checks が登録されるのを待ってから監視する（PowerShell 版．Issue #133）．
#
# 実行列と終了コードは bin/watch-pr-checks.sh と同一
# （同スクリプトのヘッダーコメントを参照）．

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$Pr,

  [int]$TimeoutSeconds = 600,

  [int]$IntervalSeconds = 10,

  [string]$ExpectSha = ''
)

$ErrorActionPreference = 'Stop'

# --- 入力検証 ---

if ($Pr -notmatch '^[0-9]+$') {
  Write-Error "pr-number must be a positive integer: ${Pr}"
  exit 1
}

if ($TimeoutSeconds -lt 0) {
  Write-Error "-TimeoutSeconds must be non-negative: ${TimeoutSeconds}"
  exit 1
}

if ($IntervalSeconds -lt 0) {
  Write-Error "-IntervalSeconds must be non-negative: ${IntervalSeconds}"
  exit 1
}

if ($ExpectSha -ne '' -and $ExpectSha -notmatch '^[0-9a-f]{40}$') {
  Write-Error "-ExpectSha must be a full 40-hex SHA: ${ExpectSha}"
  exit 1
}

# --- 監視対象 commit の確定 ---

# gh は push 直後に古い head を返すことがある．遅れない側である origin の
# 実体を正とし，gh の側をそこへ追いつかせる
if ($ExpectSha -eq '') {
  $Branch = gh pr view $Pr --json headRefName --jq .headRefName
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Branch)) {
    Write-Error "could not resolve the head branch of PR #${Pr}"
    exit 1
  }
  $Branch = $Branch.Trim()
  $RemoteLine = git ls-remote origin "refs/heads/${Branch}"
  $ExpectSha = if ($RemoteLine) { ($RemoteLine -split "`t")[0] } else { '' }
  if ($ExpectSha -eq '') {
    Write-Error "branch ${Branch} not found on origin (push it first)"
    exit 1
  }
  Write-Output "watch-pr-checks: target commit ${ExpectSha} (branch ${Branch})"
} else {
  Write-Output "watch-pr-checks: target commit ${ExpectSha}"
}

# --- 待機 ---

# gh の失敗を「条件未成立」と区別できないまま待ち続けると，認証切れが
# 単なるタイムアウトに見える．最後の stderr を残してタイムアウト時に示す
$Script:LastError = ''
$Script:ErrPath = [System.IO.Path]::GetTempFileName()

function Invoke-GhQuery {
  param([string[]]$GhArgs)

  # pending・failure でも gh は結果を出しつつ非 0 で終える（pending は exit 8）．
  # 終了コードで判定すると検査中の PR を照会失敗と誤読するため，出力だけを見る
  $out = & gh @GhArgs 2> $Script:ErrPath
  $text = ($out | Out-String).Trim()
  if ($text -eq '' -and (Test-Path $Script:ErrPath)) {
    $err = Get-Content -Raw $Script:ErrPath
    if (-not [string]::IsNullOrWhiteSpace($err)) {
      $Script:LastError = $err.Trim()
    }
  }
  return $text
}

function Get-HeadOid {
  return Invoke-GhQuery @('pr', 'view', $Pr, '--json', 'headRefOid', '--jq', '.headRefOid')
}

function Test-HeadMatch {
  return (Get-HeadOid) -eq $ExpectSha
}

function Get-ChecksCount {
  $text = Invoke-GhQuery @('pr', 'checks', $Pr, '--json', 'name,state', '--jq', 'length')
  if ($text -match '^[0-9]+$') {
    return [int]$text
  }
  # 数値以外（照会失敗・空）は 0 件として扱い，未登録と同じ経路へ落とす
  return 0
}

function Test-ChecksRegistered {
  return (Get-ChecksCount) -gt 0
}

function Wait-Until {
  param(
    [string]$Description,
    [scriptblock]$Condition
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ($true) {
    if (& $Condition) {
      return
    }
    if ((Get-Date) -ge $deadline) {
      Write-Output "error: timed out waiting for ${Description} (commit ${ExpectSha})"
      if ($Script:LastError -ne '') {
        Write-Output 'error: last gh error was:'
        Write-Output $Script:LastError
      }
      exit 2
    }
    if ($IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }
}

try {
  Write-Output 'watch-pr-checks: waiting for gh to catch up with origin'
  Wait-Until -Description 'gh to report the target commit' -Condition { Test-HeadMatch }

  Write-Output 'watch-pr-checks: waiting for checks to be registered'
  Wait-Until -Description 'checks to be registered' -Condition { Test-ChecksRegistered }

  # --- 監視 ---

  # workflow ごとに登録の時刻が異なるため，先に見えていた check だけで watch が
  # 完了しうる．件数が増えていれば，遅れて現れた check を含めて watch し直す．
  # 最後の照会より後に現れる check までは追えない．そこまで要るなら
  # GitHub 側の required checks 設定で担保する
  $WatchDeadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $WatchStatus = 0
  while ($true) {
    $CountBefore = Get-ChecksCount
    gh pr checks $Pr --watch
    $WatchStatus = $LASTEXITCODE
    $CountAfter = Get-ChecksCount
    if ($CountAfter -le $CountBefore) {
      break
    }
    Write-Output "watch-pr-checks: checks grew from ${CountBefore} to ${CountAfter}; watching again"
    if ((Get-Date) -ge $WatchDeadline) {
      Write-Output "error: checks kept appearing until the timeout (commit ${ExpectSha})"
      exit 2
    }
  }

  # watch 中に新しい push があれば，結果は別 commit のものである
  $AfterOid = Get-HeadOid
  if ($AfterOid -ne $ExpectSha) {
    Write-Output "error: head moved to ${AfterOid} while watching ${ExpectSha}"
    Write-Output 'error: rerun to watch the new commit'
    exit 2
  }

  if ($WatchStatus -ne 0) {
    Write-Output "error: checks did not pass on ${ExpectSha} (gh exit ${WatchStatus})"
    exit 3
  }

  Write-Output "watch-pr-checks: all checks passed on ${ExpectSha}"
} finally {
  if (Test-Path $Script:ErrPath) {
    Remove-Item -Force -ErrorAction SilentlyContinue $Script:ErrPath
  }
}
