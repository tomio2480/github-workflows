# 🧪 検査が「何も検査していない」状態をどう見つけるか（Issue #184・#185）

## 🎯 要約

Issue #179 の残した宿題 2 件を片付けた記録である．
どちらも「gate は緑だが，守りたいものを守れていない」形であった．

Issue #184 は，5.1 依存のテストが ubuntu runner で skip される問題である．
直したはずの不具合を CI が検出できない．
windows runner の job を足して解いた．

Issue #185 は，`Invoke-NativeCommand` を通さない直接呼びに関する問題である．
AST による検査を新設して解いた．

対応は PR #186（`v2.19.0`）と PR #188（`v2.19.1`）．

得た知見のうち大きいものは 3 つある．

1. **変異確認は，変異の選び方で価値が決まる．**
   雑に壊すと，証明したい経路以外も壊れて何も示せない．
2. **終了コードの判定を自前へ移すと，フレームワークが見ていた失敗種別を落とす．**
3. **検査を書いたら，通り抜ける書き方を自分で列挙して実測する．**
   テストが全件緑の状態から，抜け穴と偽陽性が計 10 件出た．

## 🗺 目次

- 🪟 skip されたまま緑になる（#184）
- 🔬 変異の選び方で証明できることが変わる
- 🚪 終了コードを自前で決めたときに落としたもの
- 🕸 AST 検査の抜け穴と偽陽性（#185）
- 🔎 bypass probe を先に作る
- 🤖 Codex レビューの頼み方で返るものが変わる
- 📎 参照

## 🪟 skip されたまま緑になる（#184）

`shell-quality` は ubuntu runner でしか走っていなかった．
5.1 を要する Pester ケースは `powershell.exe` の有無で自ら skip する．
ubuntu には無いため，2 件が飛んでいた．

```text
Tests Passed: 52, Failed: 0, Skipped: 2
```

Issue #179 で直した不具合そのものを，CI が検出できない状態であった．

検討した 3 案のうち「PowerShell 専用の windows job を分ける」を採った．
`bin/verify-shell.py` へ `--powershell-only` を足す．
既定 off の boolean input `windows-verify` で job を並べる．
ShellCheck と shfmt を Windows へ載せず，CRLF の差異も持ち込まない．

### 同じ形の穴を新設 job へ残さない

セルフレビューで指摘を受けた．新しい job も，対象 0 件なら緑で終わる．
`--powershell-only` では次の 2 つを失敗にした．

- Pester の対象が 0 件
- skip されたテストが 1 件でもある（`bin/run-pester.ps1 -FailOnSkipped`）

この 2 つを ubuntu 側へは広げていない．
そちらは PowerShell 資産を持たない caller も通る汎用の gate である．
対象 0 件も 5.1 不在の skip も，そこでは正常な状態に当たる．
`windows-verify` を有効にすること自体が
「5.1 を要するテストを持つ」という宣言であり，非対称はそこに根拠がある．

## 🔬 変異の選び方で証明できることが変わる

受け入れ条件に「ヘルパーの緩和を消したときに CI が落ちること」があった．
最初は素直に `bin/lib/native.ps1` の緩和を丸ごと消した．

| job | 結果 |
|---|---|
| ubuntu | fail（1 件）．`scriptblock の内側では停止設定を緩める` |
| windows | fail（3 件） |

両方落ちた．**しかしこれでは windows job の価値を示せていない．**
ubuntu が捕まえたのは機構の検査だけである．
機構の検査は 5.1 が無くても動くため，windows job が無くても落ちた．

緩和を PowerShell 7 に限定する形へ変異を差し替えた．

```powershell
if ($PSVersionTable.PSVersion.Major -ge 7) { $ErrorActionPreference = 'Continue' }
```

| job | 結果 |
|---|---|
| ubuntu | **pass** |
| windows | **fail**（2 件） |

5.1 の振る舞いだけが壊れる変異では，ubuntu は素通りし windows だけが落ちた．
ここで初めて「5.1 依存の回帰を CI が検出できるようになった」と言える．

**変異は，証明したい経路だけを壊す形に設計する．**
広く壊すと，他の検査も落ちて何が効いたのか分からない．

## 🚪 終了コードを自前で決めたときに落としたもの

`-FailOnSkipped` を実装するため，`bin/run-pester.ps1` を書き替えた．
`Run.Exit = $true` をやめ，`PassThru` の結果から自分で `exit` する．
skip の判定より先に process が抜けてしまうためである．

このとき `$result.FailedCount -gt 0` で判定した．これが回帰であった．

| 入力 | 変更前 | 変更後 | 修正後 |
|---|---:|---:|---:|
| 成功する suite | 0 | 0 | 0 |
| 失敗する suite | 1 | 1 | 1 |
| discovery 失敗（閉じ括弧欠け） | 1 | **0** | 1 |
| 対象が 1 件も無い path | -1 | **0** | 1 |

Pester は container failure を次のように扱う．

```text
Result                = Failed
FailedCount           = 0
FailedContainersCount = 1
TotalCount            = 0
```

`FailedCount` は 0 のままである．件数を見る判定では拾えない．
構文の壊れたテストが CI を素通りする状態であった．

`$result.Result -ne 'Passed'` を見る形へ改めた．
`FailedContainersCount` ではなく `Result` を選んだ．
Pester 自身の総合判定であり，将来ほかの失敗種別が増えても追随する．
対象が無いときの例外も `try`／`catch` で捕まえて非 0 で終える．

**移す前後の終了コードを，入力ごとに実測して並べる．**
推測で書かない．`$LASTEXITCODE` は前の値が残るため，
1 コマンドずつ関数で包んで測る．

この回帰は Codex も P1 として挙げた．
先に気づけたのは，レビュー依頼へ
「`Run.Exit` を外して失う経路が無いか」と観点を書いていたためである．

## 🕸 AST 検査の抜け穴と偽陽性（#185）

規律は `docs/shell-quality.md` にあったが，機械で守れていなかった．
新しい `.ps1` が `Invoke-NativeCommand` を通さずに書いても gate は通る．

`bin/check-native-calls.ps1` を新設した．
`CommandAst` を辿り，包まれていない native command の呼び出しを違反とする．
包まれているとは，`Invoke-NativeCommand` の scriptblock 引数の内側を指す．
正規表現を採らなかったのは，複数行にまたがる呼び出しを取りこぼすためである．

Pester が全件緑になった状態から，抜け穴と偽陽性が計 10 件出た．
自分の実測で 3 件，Codex のレビュー 2 巡で 9 件（重複 2 件）である．

### 検出漏れ

- **文字列評価は AST に現れない．** `Invoke-Expression`，
  `$ExecutionContext.InvokeCommand.InvokeScript()`，
  `[scriptblock]::Create(...)`，`$shell.AddScript(...)`．
  後ろ 3 つは `CommandAst` ではなく `InvokeMemberExpressionAst` である．
- **名前の正規化漏れ．** `Microsoft.PowerShell.Utility\Invoke-Expression` は
  `GetCommandName()` が修飾名を返し，完全一致で躱される．
- **定義名の収集範囲．** 全ファイル共通で集めると，あるファイルの
  `function gh { }` が別ファイルの `gh` を素通りさせる．
  入れ子の定義も呼び出し位置からは見えない．
- **コメント行の判定．** 行末コメントのある行を「コメント行」と数えると，
  免除の注記が間のコードを跨いで下のコマンドへ届く．

### 偽陽性

- **メンバー名だけの判定は広すぎる．** `Create` で倒すと
  `[HashSet[string]]::Create()` を巻き込む．型と組で見る．
- **別名の解決．** `AliasInfo.ResolvedCommand` は空を返すことがある．

```text
CommandType     = Alias
ResolvedCommand = []
Definition      = Get-ChildItem
```

  `Definition` から引き直さないと，`gci` のような cmdlet の別名を
  native と誤判定する．

必須 gate は偽陽性 1 件で常に赤になる．
**検出側へ倒す判断と，倒しすぎない判断は，両方向の probe で釣り合いを見る．**

### 解決できない名前は疑う側へ倒す

native かどうかは `Get-Command` で解決して決める．
解決できない名前は native として扱う．
module 未導入などで解決に失敗したとき，黙って見逃すと
「指摘 0 件で成功」に化けるためである．

## 🔎 bypass probe を先に作る

抜け穴の探索には，疑う書き方を並べた 1 枚のファイルが効いた．
テストを書くより先にこれを作ると早い．

```powershell
git status | Select-String 'x'          # pipeline の途中
1..2 | ForEach-Object { git status }    # scriptblock の内側
try { git status } catch { }            # try の内側
$sb = { git status }                    # 変数へ入れた scriptblock
Invoke-Expression 'git status'          # 文字列評価
& $tool status                          # 間接呼び出し
if ((git rev-parse --abbrev-ref HEAD) -eq 'main') { }
$out = $(git status)                    # 部分式
```

どれが検出されるかを一覧で見る．
最初の実測では `Invoke-Expression` だけが素通りした．
偽陽性側の probe も同じ形で作る．正当なコードを並べ，落ちないことを見る．

## 🤖 Codex レビューの頼み方で返るものが変わる

過去 2 回（`v2.17.2` の PR #175，#184 の PR #186）は
「major issues なし」だけで，添えた個別観点への回答が無かった．

今回（PR #188）は 2 巡で P2 を計 9 件返し，**すべて実在した．**
違いは観点の書き方にあったと考えている．

- 疑っている前提を具体的に列挙した．
- 「この検査を通り抜ける書き方を挙げてほしい」のように，
  探すものを名指しした．漠然と「レビューして」とは書かない．
- 「各観点へ個別に答えてほしい」と明記した．

### 最新 commit を見てもらう

**Ready for Review にしても，最新 commit が対象になるとは限らない．**
PR #188 で Ready 化した．
だが Codex の最後のレビューは 2 つ前の commit のままであった．
25 分待っても新しい応答は無かった．

修正そのものが未レビューの状態でマージしかけたことになる．
明示的に `@codex review` を投げ，対象 commit を本文へ書いてから待った．
結果として P2 が 4 件出た．CI 緑だけでマージしていたら，
検査を素通りする経路が 4 つ残っていた．

リアクションの意味も押さえておく．

- 👀（eyes）は受領であり，処理中である．
- 👍（+1）は「指摘なし」で完了した合図である．
- 監視するときは review・inline comment・issue comment・reaction の
  4 つを見る．review だけを数えると取りこぼす．

## 📎 参照

- Issue #184・#185．PR #186（`v2.19.0`）・PR #188（`v2.19.1`）．
- 前提となる経緯は
  [2026-09-04-issue179-native-stderr.md](2026-09-04-issue179-native-stderr.md) にある．
- 規律の本体は [shell-quality.md](../shell-quality.md) にある．
  該当は「native command の呼び出し規律」節と「任意の windows job」節である．
