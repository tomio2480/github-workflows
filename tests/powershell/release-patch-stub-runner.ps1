# bin/release-patch.ps1 を git・gh のスタブつきで実行する（テスト用）．
#
# PATH へ実行ファイルを置く代わりに，同一セッションで関数を定義して
# 外部コマンドを覆う．方式は tests/powershell/stub-runner.ps1 と同じである．
#
# スタブの挙動は環境変数で制御する．既定は「順調な初回リリース」とする．
#   STUB_LOG                    発行コマンドの記録先（必須）
#   STUB_TAG_EXISTS             1 で refs/tags/<version> が既に在る
#   STUB_TAG_SHA                既存タグが指す SHA（既定は要求と異なる SHA）
#   STUB_COMMIT_MISSING         1 で merge-sha がローカルに無い
#   STUB_SHALLOW                1 で shallow クローン
#   STUB_REMOTE_MAJOR_ABSENT    1 で remote に major mutable タグが無い
#   STUB_LS_REMOTE_FAILS        1 で ls-remote 自体が失敗する
#   STUB_MAJOR_NOT_ANCESTOR     1 で remote major が新 patch の祖先でない
#   STUB_RELEASE_EXISTS         1 で Release が既に在る

# param ブロックは置かない．対象スクリプト側の引数名が共通パラメーターの
# 前方一致で吸われるためである．自動変数 $args ならそのまま素通しできる．

$ErrorActionPreference = 'Stop'

$RemoteMajorSha = '1111111111111111111111111111111111111111'
$OtherSha = 'ffffffffffffffffffffffffffffffffffffffff'

function Write-StubLog {
  param([string]$Line)
  Add-Content -LiteralPath $env:STUB_LOG -Value $Line
}

# 対象スクリプトは & 'git' @(...) の形で呼ぶ．native command なら配列は
# 個々の引数へ展開されるが，関数へは配列 1 個として渡る．実物と同じ列を
# 見るため，1 段だけ平坦化する
function ConvertTo-StubArgs {
  param([object[]]$Raw)
  return @($Raw | ForEach-Object { $_ })
}

# param ブロックを持たせない．-e・-q のような短いオプションが共通パラメーター
# （-ErrorAction 等）の前方一致で吸われるためである．自動変数 $args なら
# 素通しできる．対象スクリプトは実物と同じ引数列を渡す
function git {
  $GitArgs = ConvertTo-StubArgs $args

  Write-StubLog ('git ' + ($GitArgs -join ' '))
  $global:LASTEXITCODE = 0

  switch ($GitArgs[0]) {
    'rev-parse' {
      if ($GitArgs -contains '--is-shallow-repository') {
        if ($env:STUB_SHALLOW -eq '1') { return 'true' }
        return 'false'
      }
      # refs/tags/<version> の存在確認．既定は未存在（非 0 で終える）
      if ($env:STUB_TAG_EXISTS -eq '1') {
        if ([string]::IsNullOrEmpty($env:STUB_TAG_SHA)) { return $OtherSha }
        return $env:STUB_TAG_SHA
      }
      $global:LASTEXITCODE = 1
      return
    }
    'cat-file' {
      # commit の実在確認．既定は存在する
      if ($env:STUB_COMMIT_MISSING -eq '1') {
        $global:LASTEXITCODE = 1
      }
      return
    }
    'ls-remote' {
      # 照会そのものの失敗．出力なしの点は「タグが無い」と同じで，
      # 終了コードだけが異なる．lease 無し push へ落とさない
      if ($env:STUB_LS_REMOTE_FAILS -eq '1') {
        [Console]::Error.WriteLine('fatal: could not read Username')
        $global:LASTEXITCODE = 128
        return
      }
      if ($env:STUB_REMOTE_MAJOR_ABSENT -eq '1') { return }
      return "${RemoteMajorSha}`t$($GitArgs[2])"
    }
    'merge-base' {
      # 単調性検査．既定は remote が新 patch の祖先である
      if ($env:STUB_MAJOR_NOT_ANCESTOR -eq '1') {
        $global:LASTEXITCODE = 1
      }
      return
    }
  }
}

function gh {
  $GhArgs = ConvertTo-StubArgs $args

  Write-StubLog ('gh ' + ($GhArgs -join ' '))
  $global:LASTEXITCODE = 0

  if ($GhArgs[0] -eq 'release' -and $GhArgs[1] -eq 'view') {
    if ($env:STUB_RELEASE_EXISTS -eq '1') { return }
    # 実物は未作成時に stderr へ書いて非 0 で終える．この経路は想定内であり，
    # 終了コードで分岐する（Issue #179 の発生箇所）
    [Console]::Error.WriteLine('release not found')
    $global:LASTEXITCODE = 1
    return
  }
}

$global:LASTEXITCODE = 0

& (Join-Path $PSScriptRoot '../../bin/release-patch.ps1') @args

if ($null -eq $LASTEXITCODE) {
  exit 0
}
exit $LASTEXITCODE
