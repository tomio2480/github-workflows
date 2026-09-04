# bin/check-native-calls.ps1 の単体テスト（Pester）．
#
# 「終了コードで分岐する native command は Invoke-NativeCommand 経由で呼ぶ」
# という規律を，機械で守れているかを検査する（Issue #185）．
#
# 文書に書いただけでは別セッションの自分に届かない．
# v2.16.1 と v2.17.2 で同じ穴を 2 度踏んでいる．

BeforeAll {
  $script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
  $script:Checker = Join-Path $script:RepoRoot 'bin/check-native-calls.ps1'
  $script:FixtureDir = Join-Path $PSScriptRoot 'fixtures/native-calls'

  function Invoke-Checker {
    param([string[]]$Fixture)

    $arguments = @('-NoProfile', '-File', $script:Checker)
    foreach ($name in $Fixture) {
      $arguments += (Join-Path $script:FixtureDir $name)
    }
    $output = & pwsh @arguments 2>&1
    return [pscustomobject]@{
      ExitCode = $LASTEXITCODE
      Output   = ($output | Out-String)
    }
  }
}

Describe 'bin/check-native-calls.ps1' {
  It '規律を守った .ps1 は通す' {
    (Invoke-Checker -Fixture 'compliant.ps1').ExitCode | Should -Be 0
  }

  It '直接呼びを検出して非 0 を返す' {
    $result = Invoke-Checker -Fixture 'violation.ps1'

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'gh'
  }

  It '検出箇所の行番号を示す' {
    # 指摘だけでは直せない．どこかを言う
    (Invoke-Checker -Fixture 'violation.ps1').Output | Should -Match 'violation\.ps1:5'
  }

  It 'native-direct の注記がある直接呼びは通す' {
    $result = Invoke-Checker -Fixture 'excepted.ps1'

    $result.ExitCode | Should -Be 0
    # 終了コードだけでは，検査が動かなかった場合と区別できない
    $result.Output | Should -Match 'no unwrapped native command call'
  }

  It '複数行の注記でも直上の塊なら免除する' {
    # 理由を 1 行へ収められないことがある．塊の先頭に注記があればよい
    $result = Invoke-Checker -Fixture 'multiline-note.ps1'

    $result.Output | Should -Not -Match 'multiline-note\.ps1:7'
  }

  It '空行で切れた注記は届かない' {
    $result = Invoke-Checker -Fixture 'multiline-note.ps1'

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'multiline-note\.ps1:13'
  }

  It 'Invoke-Expression による迂回を許さない' {
    # 文字列の中身は AST に現れない．native command か判定できないため，
    # 文字列評価そのものを違反とする
    $result = Invoke-Checker -Fixture 'invoke-expression.ps1'

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'invoke-expression\.ps1:6'
    # 別名でも同じ
    $result.Output | Should -Match 'invoke-expression\.ps1:8'
  }

  It '解決できない名前も native として扱う' {
    # ツール未導入で解決に失敗したとき，黙って見逃すと
    # 「指摘 0 件で成功」に化ける
    $result = Invoke-Checker -Fixture 'unresolved.ps1'

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'zz-not-a-real-command'
  }

  It '文字列の中の注記では免除しない' {
    # 免除は comment token だけを見る
    (Invoke-Checker -Fixture 'literal-marker.ps1').ExitCode | Should -Not -Be 0
  }

  It '別ファイルの関数定義で名前を隠せない' {
    # 定義はファイルを跨いで見えない．全ファイル共通で集めると素通りする
    $result = Invoke-Checker -Fixture @('shadow-definition.ps1', 'violation.ps1')

    $result.Output | Should -Match 'violation\.ps1:5'
  }

  It '行末コメントのある行では注記の塊が切れる' {
    $result = Invoke-Checker -Fixture 'trailing-comment.ps1'

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'trailing-comment\.ps1:8'
  }

  It 'メンバー呼び出しによる文字列評価も違反とする' {
    # CommandAst に現れない．Invoke-Expression を塞ぐだけでは足りない
    $result = Invoke-Checker -Fixture 'dynamic-eval.ps1'

    $result.ExitCode | Should -Not -Be 0
    $result.Output | Should -Match 'dynamic-eval\.ps1:5'
    $result.Output | Should -Match 'dynamic-eval\.ps1:7'
  }

  It 'Create という名前だけでは違反にしない' {
    # 型を見ないと HashSet[string]::Create() まで巻き込む
    (Invoke-Checker -Fixture 'dynamic-eval.ps1').Output |
      Should -Not -Match 'dynamic-eval\.ps1:10'
  }

  It '複数ファイルのうち 1 つでも違反があれば落ちる' {
    (Invoke-Checker -Fixture @('compliant.ps1', 'violation.ps1')).ExitCode |
      Should -Not -Be 0
  }

  It '本リポジトリの bin/ 配下は現状すべて通る' {
    # 規律は既に守られている．検査の側が偽陽性を出さないことを見る
    $arguments = @('-NoProfile', '-File', $script:Checker)
    $targets = @(
      Get-ChildItem (Join-Path $script:RepoRoot 'bin/*.ps1') -File
      Get-ChildItem (Join-Path $script:RepoRoot 'bin/lib/*.ps1') -File
    )
    foreach ($target in $targets) {
      $arguments += $target.FullName
    }

    $output = & pwsh @arguments 2>&1
    $code = $LASTEXITCODE

    if ($code -ne 0) {
      Write-Host ($output | Out-String)
    }
    $code | Should -Be 0
  }
}
