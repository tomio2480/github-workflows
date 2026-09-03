# bin/watch-pr-checks.ps1 を gh・git のスタブつきで実行する（テスト用）．
#
# PATH へ実行ファイルを置く代わりに，同一セッションで関数を定義して
# 外部コマンドを覆う．関数の探索は呼び出し元のスコープまで遡るため，
# 対象スクリプトからは gh・git がこの関数に見える．
# 実行ファイルの拡張子や実行権限に依存しないため，Windows と Linux で
# 同じ手順が使える．
#
# スタブの挙動は環境変数で制御する．
#   STUB_LOG            発行コマンドの記録先（必須）
#   STUB_STATE_DIR      呼び出し回数の記録先（必須）
#   STUB_REMOTE_EMPTY   1 で「ブランチが remote に無い」
#   STUB_REMOTE_FAILS   1 で ls-remote 自体が失敗する
#   STUB_GH_LAG         gh が古い SHA を返し続ける回数
#   STUB_CHECKS_LAG     checks が未登録（出力なし）の回数
#   STUB_CHECKS         pass / fail / pending / late / growing
#   STUB_HEAD_MOVES     1 で checks 照会後の headRefOid を別 commit にする
#   STUB_CROSS_REPO     1 で fork からの PR を再現する

# param ブロックは置かない．-Pr のような対象スクリプト側の引数名が
# 共通パラメーター（-ProgressAction 等）の前方一致で吸われるためである．
# 自動変数 $args ならそのまま素通しできる．

$ErrorActionPreference = 'Stop'

$RemoteSha = '1111111111111111111111111111111111111111'
$StaleSha = '2222222222222222222222222222222222222222'

function Write-StubLog {
  param([string]$Line)
  Add-Content -LiteralPath $env:STUB_LOG -Value $Line
}

function Step-StubCounter {
  param([string]$Name)
  $file = Join-Path $env:STUB_STATE_DIR $Name
  $n = 0
  if (Test-Path -LiteralPath $file) {
    $n = [int](Get-Content -LiteralPath $file -Raw).Trim()
  }
  $n = $n + 1
  Set-Content -LiteralPath $file -Value $n
  return $n
}

function Get-StubEnvInt {
  param([string]$Name)
  $value = [Environment]::GetEnvironmentVariable($Name)
  if ([string]::IsNullOrWhiteSpace($value)) {
    return 0
  }
  return [int]$value
}

function git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)

  Write-StubLog ('git ' + ($GitArgs -join ' '))
  if ($GitArgs[0] -eq 'ls-remote') {
    # 照会そのものの失敗．出力なしの点は「ブランチが無い」と同じで，
    # 終了コードだけが異なる
    if ($env:STUB_REMOTE_FAILS -eq '1') {
      [Console]::Error.WriteLine('fatal: could not read Username')
      $global:LASTEXITCODE = 128
      return
    }
    if ($env:STUB_REMOTE_EMPTY -eq '1') {
      return
    }
    return "${RemoteSha}`t$($GitArgs[2])"
  }
}

function gh {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GhArgs)

  $joined = $GhArgs -join ' '
  Write-StubLog ('gh ' + $joined)

  # 実物の gh は --json をカンマ区切りの 1 引数として受け取り，位置引数が
  # 増えると拒否する．PowerShell が引用符なしのカンマを配列へ分割する事故を
  # 検出するため，スタブでも同じ厳しさを持たせる（2026-09-02 の実害）
  $jsonIndex = [array]::IndexOf($GhArgs, '--json')
  $jsonFields = ''
  if ($jsonIndex -ge 0 -and ($jsonIndex + 1) -lt $GhArgs.Count) {
    $jsonFields = $GhArgs[$jsonIndex + 1]
  }
  if ($jsonIndex -ge 0 -and $jsonFields -notmatch '^[A-Za-z]+(,[A-Za-z]+)*$') {
    Write-Error 'gh: accepts at most 1 arg(s)'
    return
  }

  if ($GhArgs[0] -eq 'pr' -and $GhArgs[1] -eq 'view') {
    if ($joined -like '*headRefName*') {
      # 実物は --jq で TSV へ畳んだ 4 列を返す
      if ($env:STUB_CROSS_REPO -eq '1') {
        return "feature/example`ttrue`tforker`tgithub-workflows"
      }
      return "feature/example`tfalse`ttomio2480`tgithub-workflows"
    }
    if ($joined -like '*headRefOid*') {
      # checks を 1 度でも照会した後は「監視の後」とみなす
      $queried = Test-Path -LiteralPath (Join-Path $env:STUB_STATE_DIR 'checks')
      if ($env:STUB_HEAD_MOVES -eq '1' -and $queried) {
        return $StaleSha
      }
      $n = Step-StubCounter -Name 'view'
      if ($n -le (Get-StubEnvInt -Name 'STUB_GH_LAG')) {
        return $StaleSha
      }
      return $RemoteSha
    }
    return
  }

  if ($GhArgs[0] -eq 'pr' -and $GhArgs[1] -eq 'checks') {
    $n = Step-StubCounter -Name 'checks'
    $lag = Get-StubEnvInt -Name 'STUB_CHECKS_LAG'
    if ($n -le $lag) {
      # 未登録は出力なし
      return
    }
    switch ($env:STUB_CHECKS) {
      'fail' {
        return @('pass', 'fail')
      }
      'pending' {
        # 最初の 2 回だけ pending を含む
        if ($n -le ($lag + 2)) {
          return @('pending', 'pass')
        }
        return @('pass', 'pass')
      }
      'late' {
        # 2 回目の照会で 2 件目が現れる
        if ($n -le ($lag + 1)) {
          return @('pass')
        }
        return @('pass', 'pass')
      }
      'lateslow' {
        # 3 回目の照会で 2 件目が現れる．件数の据え置き 1 回では拾えない
        if ($n -le ($lag + 2)) {
          return @('pass')
        }
        return @('pass', 'pass')
      }
      'skip' {
        return @('pass', 'skipping')
      }
      'allskip' {
        return @('skipping', 'skipping')
      }
      'growing' {
        # 照会のたびに 1 件増え続け，件数が安定しない
        return @(1..$n | ForEach-Object { 'pass' })
      }
      default {
        return @('pass', 'pass')
      }
    }
  }
}

# 対象スクリプトは gh の終了コードを 1 箇所で見る．関数のスタブは
# $LASTEXITCODE を触らないため，実行前に成功で初期化しておく
$global:LASTEXITCODE = 0

& (Join-Path $PSScriptRoot '../../bin/watch-pr-checks.ps1') @args

# & で呼んだスクリプトの exit は呼び出し元を終わらせない．終了コードは
# $LASTEXITCODE へ入るため，それを子プロセスの終了コードとして返す
if ($null -eq $LASTEXITCODE) {
  exit 0
}
exit $LASTEXITCODE
