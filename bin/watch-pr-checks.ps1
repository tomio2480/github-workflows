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

  [string]$ExpectSha = '',

  [ValidateSet('full', 'summary', 'json')]
  [string]$Format = 'full',

  [ValidateRange(0, 999999999)]
  [int]$Limit = 20,

  [string]$OutputDir = ''
)

$ErrorActionPreference = 'Stop'

# 終了コードで分岐する native command は Invoke-NativeCommand 経由で呼ぶ．
# 直接呼ぶと Windows PowerShell 5.1 で stderr が終了エラーへ昇格する（Issue #179）
. (Join-Path $PSScriptRoot 'lib/native.ps1')

$Script:RunDir = ''
$Script:WatchExit = 1
$Script:Reason = 'error'
$Script:Utf8 = New-Object System.Text.UTF8Encoding($false)
$Format = $Format.ToLowerInvariant()

function Write-WatchOutput {
  param([string]$Message)
  if ($Script:RunDir -ne '') {
    [IO.File]::AppendAllText((Join-Path $Script:RunDir 'full.txt'), "$Message`n", $Script:Utf8)
  }
  if ($Script:RunDir -eq '' -or $Format -eq 'full') { Write-Output $Message }
}

function Write-Failure {
  # -Recorded は記録係が diagnostics.log へ書き終えた本文であり，表示だけを足す
  param([string]$Message, [switch]$Recorded)
  if ($Script:RunDir -ne '' -and -not $Recorded) {
    [IO.File]::AppendAllText((Join-Path $Script:RunDir 'diagnostics.log'), "$Message`n", $Script:Utf8)
  }
  if ($Script:RunDir -eq '' -or $Format -eq 'full') { [Console]::Error.WriteLine($Message) }
}

# --- 入力検証 ---

if ($Pr -notmatch '^[0-9]+$') {
  Write-Failure "pr-number must be a positive integer: ${Pr}"
  exit 1
}

if ($TimeoutSeconds -lt 0) {
  Write-Failure "-TimeoutSeconds must be non-negative: ${TimeoutSeconds}"
  exit 1
}

if ($IntervalSeconds -lt 0) {
  Write-Failure "-IntervalSeconds must be non-negative: ${IntervalSeconds}"
  exit 1
}

if ($SettleSeconds -lt 0) {
  Write-Failure "-SettleSeconds must be non-negative: ${SettleSeconds}"
  exit 1
}

# settle が timeout を超えると，どれだけ静かでも必ずタイムアウトする
if ($SettleSeconds -gt $TimeoutSeconds) {
  Write-Failure "-SettleSeconds (${SettleSeconds}) must not exceed -TimeoutSeconds (${TimeoutSeconds})"
  exit 1
}

# 間隔 0 で据え置きを待つと，その間 API を全速で叩き続ける
if ($IntervalSeconds -eq 0 -and $SettleSeconds -gt 0) {
  Write-Failure '-IntervalSeconds 0 requires -SettleSeconds 0 (it would busy-poll the API)'
  exit 1
}

if ($ExpectSha -ne '' -and $ExpectSha -notmatch '^[0-9a-f]{40}$') {
  Write-Failure "-ExpectSha must be a full 40-hex SHA: ${ExpectSha}"
  exit 1
}

# --- 監視対象 commit の確定 ---

if ($Format -ne 'full' -or $OutputDir -ne '') {
  $Script:Python = ''
  foreach ($candidate in @('python3', 'python')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
      Invoke-NativeCommand { & $args[0] -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>$null } -ArgumentList @($candidate)
      if ($LASTEXITCODE -eq 0) { $Script:Python = $candidate; break }
    }
  }
  if ($Script:Python -eq '') { Write-Failure 'record mode requires Python 3.9+'; exit 1 }
  [Console]::OutputEncoding = $Script:Utf8
  $Script:Recorder = Join-Path $PSScriptRoot '../scripts/watch-checks-record.py'
  $initArgs = @('-X', 'utf8', $Script:Recorder, 'init', '--timeout', [string]$TimeoutSeconds,
    '--interval', [string]$IntervalSeconds, '--settle', [string]$SettleSeconds)
  if ($OutputDir -ne '') { $initArgs += @('--output-dir', $OutputDir) }
  $directory = Invoke-NativeCommand { & $Script:Python @args } -ArgumentList $initArgs
  if ($LASTEXITCODE -ne 0) { exit 1 }
  $Script:RunDir = ($directory | Out-String).Trim()
}

$Script:LastError = ''
$Script:ErrPath = [System.IO.Path]::GetTempFileName()

function Invoke-GhQuery {
  param([string[]]$GhArgs, [string]$Kind = 'head')

  if ($Script:RunDir -ne '') {
    $recordArgs = @('-X', 'utf8', $Script:Recorder, 'query', $Script:RunDir, $Kind, 'gh') + $GhArgs
    $out = Invoke-NativeCommand { & $Script:Python @args 2> $Script:ErrPath } -ArgumentList $recordArgs
  } else {
    $out = Invoke-NativeCommand { & gh @args 2> $Script:ErrPath } -ArgumentList $GhArgs
  }
  $text = ($out | Out-String).Trim()
  if (Test-Path -LiteralPath $Script:ErrPath) {
    $err = Get-Content -LiteralPath $Script:ErrPath -Raw
    if (-not [string]::IsNullOrWhiteSpace($err)) { $Script:LastError = $err.Trim() }
  }
  return $text
}

try {

  # gh は push 直後に古い head を返すことがある．遅れない側であるリモートの
  # 実体を正とし，gh の側をそこへ追いつかせる．
  #
  # fork からの PR では head ブランチが origin に無い．同名のブランチが base に
  # あると，無関係な commit を掴んだまま待つ．head の所属先を解決してから引く
  if ($ExpectSha -eq '') {
    # --json の値はカンマ区切りの 1 引数である．引用符で括らないと PowerShell が
    # カンマで配列へ分割し，gh が「引数が多い」と拒否する
    $Fields = Invoke-GhQuery -Kind 'resolve' -GhArgs @('pr', 'view', $Pr,
      '--json', 'headRefName,isCrossRepository,headRepositoryOwner,headRepository',
      '--jq', '[.headRefName, (.isCrossRepository | tostring), .headRepositoryOwner.login, .headRepository.name] | @tsv')
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Fields)) {
      Write-Failure "could not resolve the head branch of PR #${Pr}"
      if ($Script:LastError -ne '') { Write-Failure $Script:LastError -Recorded }
      exit 1
    }
    $Parts = ($Fields | Out-String).Trim() -split "`t"
    $Branch = $Parts[0]
    $CrossRepo = if ($Parts.Count -gt 1) { $Parts[1] } else { '' }
    $HeadOwner = if ($Parts.Count -gt 2) { $Parts[2] } else { '' }
    $HeadRepo = if ($Parts.Count -gt 3) { $Parts[3] } else { '' }
    if ([string]::IsNullOrWhiteSpace($Branch)) {
      Write-Failure "could not resolve the head branch of PR #${Pr}"
      exit 1
    }

    if ($CrossRepo -eq 'true') {
      if ($HeadOwner -eq '' -or $HeadRepo -eq '') {
        Write-Failure "could not resolve the head repository of PR #${Pr}"
        exit 1
      }
      $Remote = "https://github.com/${HeadOwner}/${HeadRepo}.git"
    } else {
      $Remote = 'origin'
    }

    # 出力なしには「ブランチが無い」と「照会が失敗した」の 2 つがある．
    # 区別しないと，認証切れが push 忘れへ化ける
    $RemoteLine = Invoke-NativeCommand { git ls-remote $Remote "refs/heads/${Branch}" }
    if ($LASTEXITCODE -ne 0) {
      Write-Failure "git ls-remote ${Remote} failed while resolving ${Branch}"
      exit 1
    }
    $ExpectSha = if ($RemoteLine) { ($RemoteLine -split "`t")[0] } else { '' }
    if ($ExpectSha -eq '') {
      Write-Failure "branch ${Branch} not found on ${Remote} (push it first)"
      exit 1
    }
    Write-WatchOutput "watch-pr-checks: target commit ${ExpectSha} (branch ${Branch} on ${Remote})"
  } else {
    Write-WatchOutput "watch-pr-checks: target commit ${ExpectSha}"
  }

  # --- 問い合わせ ---

  # gh の失敗を「条件未成立」と区別できないまま待ち続けると，認証切れが
  # 単なるタイムアウトに見える．最後の stderr を残してタイムアウト時に示す
  function Get-HeadOid {
    return Invoke-GhQuery @('pr', 'view', $Pr, '--json', 'headRefOid', '--jq', '.headRefOid')
  }

  function Get-CheckBucket {
    if ($Script:RunDir -ne '') {
      $text = Invoke-GhQuery -Kind 'checks' -GhArgs @('pr', 'checks', $Pr, '--json', 'name,state,bucket,link')
    } else {
      $text = Invoke-GhQuery @('pr', 'checks', $Pr, '--json', 'name,state,bucket', '--jq', '.[].bucket')
    }
    if ($text -eq '') {
      # 出力が無い状態は「未登録」と「照会失敗」の両方を含み，どちらも待機を続ける
      return @()
    }
    return @($text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
  }

  function Write-TimeoutReport {
    param([string]$Description)
    $Script:Reason = 'timeout'
    Write-Failure "error: timed out waiting for ${Description} (commit ${ExpectSha})"
    if ($Script:LastError -ne '') {
      Write-Failure 'error: last gh error was:'
      Write-Failure $Script:LastError
    }
  }

  # --- gh がリモートへ追いつくのを待つ ---

  # -TimeoutSeconds は監視全体に掛かる．段ごとに取り直すと合計が 2 倍に
  # なりうるため，締切は 1 度だけ決めて両方の待機で使い回す
  $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  Write-WatchOutput 'watch-pr-checks: waiting for gh to catch up with the remote'
  while ((Get-HeadOid) -ne $ExpectSha) {
    if ((Get-Date) -ge $Deadline) {
      Write-TimeoutReport -Description 'gh to report the target commit'
      $Script:WatchExit = 2; exit 2
    }
    if ($IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }

  # --- checks が出そろうのを待つ ---

  # 件数が一定の時間を要求するが，settle 後の未登録 check は保証しない．
  Write-WatchOutput 'watch-pr-checks: waiting for checks to settle'
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
      Write-WatchOutput "watch-pr-checks: ${report}"
      $PrevReport = $report
    }
    $PrevTotal = $Total

    if ((Get-Date) -ge $Deadline) {
      Write-TimeoutReport -Description 'checks to settle'
      $Script:WatchExit = 2; exit 2
    }
    if ($IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }

  # --- 判定 ---

  # 監視の間に新しい push があれば，見ていた結果は別 commit のものである
  $AfterOid = Get-HeadOid
  if ($AfterOid -eq '') {
    $Script:Reason = 'head_unavailable'
    Write-Failure "error: could not re-read the head of PR #${Pr} after watching ${ExpectSha}"
    if ($Script:LastError -ne '') {
      Write-Failure $Script:LastError
    }
    $Script:WatchExit = 2; exit 2
  }
  if ($AfterOid -ne $ExpectSha) {
    $Script:Reason = 'head_changed'
    Write-Failure "error: head moved to ${AfterOid} while watching ${ExpectSha}"
    Write-Failure 'error: rerun to watch the new commit'
    $Script:WatchExit = 2; exit 2
  }

  if ($Failed -gt 0) {
    $Script:Reason = 'checks_failed'
    Write-Failure "error: ${Failed} of ${Total} checks did not pass on ${ExpectSha}"
    $Script:WatchExit = 3; exit 3
  }

  # skip した check を通過件数へ数えない．「検査した」と「検査を飛ばした」は別である．
  # すべて skip なら通過は 0 件である．これを「全 pass」と読ませると，
  # path filter の設定ミスが green として沈黙する
  $Passed = $Total - $Skipped
  if ($Skipped -eq 0) {
    Write-WatchOutput "watch-pr-checks: all ${Total} checks passed on ${ExpectSha}"
  } elseif ($Passed -eq 0) {
    Write-WatchOutput "watch-pr-checks: no checks ran on ${ExpectSha} (${Skipped} skipped)"
  } else {
    Write-WatchOutput "watch-pr-checks: all ${Passed} checks passed on ${ExpectSha} (${Skipped} skipped)"
  }
  $Script:WatchExit = 0
  $Script:Reason = 'settled'
} catch {
  Write-Failure $_.Exception.Message
  $Script:WatchExit = 1
} finally {
  if (Test-Path $Script:ErrPath) {
    Remove-Item -Force -ErrorAction SilentlyContinue $Script:ErrPath
  }
  if ($Script:RunDir -ne '') {
    $finishArgs = @('-X', 'utf8', $Script:Recorder, 'finish', '--run-dir', $Script:RunDir,
      '--code', [string]$Script:WatchExit, '--reason', $Script:Reason,
      '--pr', $Pr, '--format', $Format, '--limit', [string]$Limit)
    if ($ExpectSha -ne '') { $finishArgs += @('--expected-sha', $ExpectSha) }
    Invoke-NativeCommand { & $Script:Python @args } -ArgumentList $finishArgs
    if ($LASTEXITCODE -ne $Script:WatchExit) { exit 1 }
  }
}
exit $Script:WatchExit
