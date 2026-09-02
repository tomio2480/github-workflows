# PR の checks が出そろうまで監視する（PowerShell 版．Issue #133）．
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

# --- 問い合わせ ---

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

function Get-CheckBucket {
  $text = Invoke-GhQuery @('pr', 'checks', $Pr, '--json', 'name,state,bucket', '--jq', '.[].bucket')
  if ($text -eq '') {
    # 出力が無い状態は「未登録」と「照会失敗」の両方を含み，どちらも待機を続ける
    return @()
  }
  return @($text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

function Write-TimeoutReport {
  param([string]$Description)
  Write-Output "error: timed out waiting for ${Description} (commit ${ExpectSha})"
  if ($Script:LastError -ne '') {
    Write-Output 'error: last gh error was:'
    Write-Output $Script:LastError
  }
}

try {
  # --- gh がリモートへ追いつくのを待つ ---

  Write-Output 'watch-pr-checks: waiting for gh to catch up with origin'
  $CatchupDeadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-HeadOid) -ne $ExpectSha) {
    if ((Get-Date) -ge $CatchupDeadline) {
      Write-TimeoutReport -Description 'gh to report the target commit'
      exit 2
    }
    if ($IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }

  # --- checks が出そろうのを待つ ---

  # 完了の条件は 3 つである．1 件以上あること，pending が無いこと，件数が
  # 前回の照会から増えていないこと．3 つ目は，登録の時刻が workflow ごとに
  # 異なるためである．先に見えた check だけで「全 pass」と読む余地を消す．
  # 最後の照会より後に現れる check までは追えない．そこまで要るなら
  # GitHub 側の required checks 設定で担保する
  Write-Output 'watch-pr-checks: waiting for checks to settle'
  $ChecksDeadline = (Get-Date).AddSeconds($TimeoutSeconds)
  $PrevTotal = -1
  $PrevReport = ''
  $Total = 0
  $Failed = 0
  while ($true) {
    $buckets = Get-CheckBucket
    $Total = $buckets.Count
    $pending = @($buckets | Where-Object { $_ -eq 'pending' }).Count
    $Failed = @($buckets | Where-Object { $_ -eq 'fail' -or $_ -eq 'cancel' }).Count

    if ($Total -gt 0 -and $pending -eq 0 -and $Total -eq $PrevTotal) {
      break
    }

    $report = "${Total} registered, ${pending} pending"
    if ($report -ne $PrevReport) {
      Write-Output "watch-pr-checks: ${report}"
      $PrevReport = $report
    }
    $PrevTotal = $Total

    if ((Get-Date) -ge $ChecksDeadline) {
      Write-TimeoutReport -Description 'checks to settle'
      exit 2
    }
    if ($IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }

  # --- 判定 ---

  # 監視の間に新しい push があれば，見ていた結果は別 commit のものである
  $AfterOid = Get-HeadOid
  if ($AfterOid -ne $ExpectSha) {
    Write-Output "error: head moved to ${AfterOid} while watching ${ExpectSha}"
    Write-Output 'error: rerun to watch the new commit'
    exit 2
  }

  if ($Failed -gt 0) {
    Write-Output "error: ${Failed} of ${Total} checks did not pass on ${ExpectSha}"
    exit 3
  }

  Write-Output "watch-pr-checks: all ${Total} checks passed on ${ExpectSha}"
} finally {
  if (Test-Path $Script:ErrPath) {
    Remove-Item -Force -ErrorAction SilentlyContinue $Script:ErrPath
  }
}
