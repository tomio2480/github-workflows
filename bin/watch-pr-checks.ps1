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

  [int]$SettleSeconds = 120,

  [string]$ExpectSha = ''
)

$ErrorActionPreference = 'Stop'

# 終了コードで分岐する native command は Invoke-NativeCommand 経由で呼ぶ．
# 直接呼ぶと Windows PowerShell 5.1 で stderr が終了エラーへ昇格する（Issue #179）
. (Join-Path $PSScriptRoot 'lib/native.ps1')

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

if ($SettleSeconds -lt 0) {
  Write-Error "-SettleSeconds must be non-negative: ${SettleSeconds}"
  exit 1
}

# settle が timeout を超えると，どれだけ静かでも必ずタイムアウトする
if ($SettleSeconds -gt $TimeoutSeconds) {
  Write-Error "-SettleSeconds (${SettleSeconds}) must not exceed -TimeoutSeconds (${TimeoutSeconds})"
  exit 1
}

# 間隔 0 で据え置きを待つと，その間 API を全速で叩き続ける
if ($IntervalSeconds -eq 0 -and $SettleSeconds -gt 0) {
  Write-Error '-IntervalSeconds 0 requires -SettleSeconds 0 (it would busy-poll the API)'
  exit 1
}

if ($ExpectSha -ne '' -and $ExpectSha -notmatch '^[0-9a-f]{40}$') {
  Write-Error "-ExpectSha must be a full 40-hex SHA: ${ExpectSha}"
  exit 1
}

# --- 監視対象 commit の確定 ---

# gh は push 直後に古い head を返すことがある．遅れない側であるリモートの
# 実体を正とし，gh の側をそこへ追いつかせる．
#
# fork からの PR では head ブランチが origin に無い．同名のブランチが base に
# あると，無関係な commit を掴んだまま待つ．head の所属先を解決してから引く
if ($ExpectSha -eq '') {
  # --json の値はカンマ区切りの 1 引数である．引用符で括らないと PowerShell が
  # カンマで配列へ分割し，gh が「引数が多い」と拒否する
  $Fields = Invoke-NativeCommand {
    gh pr view $Pr `
      --json 'headRefName,isCrossRepository,headRepositoryOwner,headRepository' `
      --jq '[.headRefName, (.isCrossRepository | tostring), .headRepositoryOwner.login, .headRepository.name] | @tsv'
  }
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Fields)) {
    Write-Error "could not resolve the head branch of PR #${Pr}"
    exit 1
  }
  $Parts = ($Fields | Out-String).Trim() -split "`t"
  $Branch = $Parts[0]
  $CrossRepo = if ($Parts.Count -gt 1) { $Parts[1] } else { '' }
  $HeadOwner = if ($Parts.Count -gt 2) { $Parts[2] } else { '' }
  $HeadRepo = if ($Parts.Count -gt 3) { $Parts[3] } else { '' }
  if ([string]::IsNullOrWhiteSpace($Branch)) {
    Write-Error "could not resolve the head branch of PR #${Pr}"
    exit 1
  }

  if ($CrossRepo -eq 'true') {
    if ($HeadOwner -eq '' -or $HeadRepo -eq '') {
      Write-Error "could not resolve the head repository of PR #${Pr}"
      exit 1
    }
    $Remote = "https://github.com/${HeadOwner}/${HeadRepo}.git"
  } else {
    $Remote = 'origin'
  }

  $RemoteLine = git ls-remote $Remote "refs/heads/${Branch}"
  $ExpectSha = if ($RemoteLine) { ($RemoteLine -split "`t")[0] } else { '' }
  if ($ExpectSha -eq '') {
    Write-Error "branch ${Branch} not found on ${Remote} (push it first)"
    exit 1
  }
  Write-Output "watch-pr-checks: target commit ${ExpectSha} (branch ${Branch} on ${Remote})"
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
  $out = Invoke-NativeCommand { & gh @args 2> $Script:ErrPath } -ArgumentList $GhArgs
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

# bash 版は error 行をすべて stderr へ出す．出力先もそろえる約束に含める
function Write-Failure {
  param([string]$Message)
  [Console]::Error.WriteLine($Message)
}

function Write-TimeoutReport {
  param([string]$Description)
  Write-Failure "error: timed out waiting for ${Description} (commit ${ExpectSha})"
  if ($Script:LastError -ne '') {
    Write-Failure 'error: last gh error was:'
    Write-Failure $Script:LastError
  }
}

try {
  # --- gh がリモートへ追いつくのを待つ ---

  # -TimeoutSeconds は監視全体に掛かる．段ごとに取り直すと合計が 2 倍に
  # なりうるため，締切は 1 度だけ決めて両方の待機で使い回す
  $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  Write-Output 'watch-pr-checks: waiting for gh to catch up with the remote'
  while ((Get-HeadOid) -ne $ExpectSha) {
    if ((Get-Date) -ge $Deadline) {
      Write-TimeoutReport -Description 'gh to report the target commit'
      exit 2
    }
    if ($IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }

  # --- checks が出そろうのを待つ ---

  # 完了の条件は 4 つである．1 件以上あること，pending が無いこと，件数が前回の
  # 照会から変わっていないこと，変わらなくなってから -SettleSeconds が過ぎたこと．
  # 後ろの 2 つは，登録の時刻が workflow ごとに異なるためである．
  # 先に見えた check だけで「全 pass」と読む余地を消す．
  #
  # 待つ長さが要る．本リポジトリでは CodeRabbit の status が push 直後に付き，
  # workflow の登録は約 1 分後だった．1 間隔だけの据え置きでは，前者だけを見て
  # 「1 件が全 pass」と報告してしまう（2026-09-02 に本スクリプトで実際に発生）．
  #
  # 既定の 120 秒は観測した遅延の 2 倍である．等倍では余裕が無い．
  #
  # それでも settle より後に現れる check は追えない．そこまで要るなら
  # GitHub 側の required checks 設定で担保する（本リポジトリは未設定）
  Write-Output 'watch-pr-checks: waiting for checks to settle'
  $PrevTotal = -1
  $PrevReport = ''
  $Total = 0
  $Failed = 0
  $Skipped = 0
  $StableSince = Get-Date
  while ($true) {
    $buckets = Get-CheckBucket
    $Total = $buckets.Count
    $pending = @($buckets | Where-Object { $_ -eq 'pending' }).Count
    $Failed = @($buckets | Where-Object { $_ -eq 'fail' -or $_ -eq 'cancel' }).Count
    $Skipped = @($buckets | Where-Object { $_ -eq 'skipping' }).Count

    $now = Get-Date
    if ($Total -ne $PrevTotal) {
      $StableSince = $now
    }

    $stableFor = ($now - $StableSince).TotalSeconds
    if ($Total -gt 0 -and $pending -eq 0 -and $Total -eq $PrevTotal -and
      $stableFor -ge $SettleSeconds) {
      break
    }

    $report = "${Total} registered, ${pending} pending"
    if ($report -ne $PrevReport) {
      Write-Output "watch-pr-checks: ${report}"
      $PrevReport = $report
    }
    $PrevTotal = $Total

    if ((Get-Date) -ge $Deadline) {
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
  if ($AfterOid -eq '') {
    Write-Failure "error: could not re-read the head of PR #${Pr} after watching ${ExpectSha}"
    if ($Script:LastError -ne '') {
      Write-Failure $Script:LastError
    }
    exit 2
  }
  if ($AfterOid -ne $ExpectSha) {
    Write-Failure "error: head moved to ${AfterOid} while watching ${ExpectSha}"
    Write-Failure 'error: rerun to watch the new commit'
    exit 2
  }

  if ($Failed -gt 0) {
    Write-Failure "error: ${Failed} of ${Total} checks did not pass on ${ExpectSha}"
    exit 3
  }

  # skip した check を通過件数へ数えない．「検査した」と「検査を飛ばした」は別である．
  # すべて skip なら通過は 0 件である．これを「全 pass」と読ませると，
  # path filter の設定ミスが green として沈黙する
  $Passed = $Total - $Skipped
  if ($Skipped -eq 0) {
    Write-Output "watch-pr-checks: all ${Total} checks passed on ${ExpectSha}"
  } elseif ($Passed -eq 0) {
    Write-Output "watch-pr-checks: no checks ran on ${ExpectSha} (${Skipped} skipped)"
  } else {
    Write-Output "watch-pr-checks: all ${Passed} checks passed on ${ExpectSha} (${Skipped} skipped)"
  }
} finally {
  if (Test-Path $Script:ErrPath) {
    Remove-Item -Force -ErrorAction SilentlyContinue $Script:ErrPath
  }
}
