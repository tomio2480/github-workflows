# 🪞 配る物が，自分の検査の前提を壊す（Issue #149）

## 要約

caller 向けの gate 雛形を配った（`v2.22.0`）．その雛形と対で配る helper が，
雛形自身の「検査対象があるか」という判定へ紛れ込んでいた．
`.ps1` を持つ caller が glob を書き換え忘れても，helper だけを解析して緑で終わる．
偶発ではなく既定の挙動である．
本ノートは，配布物を足すときに見るべき点を残す．

## 目次

- 🕳 何が起きたか
- 🔍 なぜ自分で見つけられなかったか
- 📏 同じ形がもう 1 つあった
- 🧭 配布物を足すときに見る
- 📚 参照

## 🕳 何が起きたか

雛形（`templates/verify-shell.py`）には，検査対象が 1 件も無いときに失敗する
guard を置いた．glob の書き換え漏れが「指摘 0 件で成功」に化けるのを
止めるためである．この判断自体は正しい．

同時に，PSScriptAnalyzer の実行部も配る設計にした．
配布元は `templates/analyze-powershell.ps1` である．
caller は `bin/analyze-powershell.ps1` として置く．

**この helper は，雛形の既定 glob `bin/*.ps1` へ自分で当たる．**

結果として次が起きる．caller が `.ps1` を `src/` へ置いており，
`POWERSHELL_PATTERNS` を書き換え忘れたとする．
glob に当たるのは helper 1 件だけになる．
対象が非空であるため guard は通る．
PSScriptAnalyzer は helper だけを解析し，指摘が無いので 0 で終わる．

**caller の実資産は 1 件も検査されないまま，gate は緑になる．**

条件が揃ったときだけ起きる偶発ではない．
helper を置いた caller では，PowerShell 側の対象が空になることが
**構造上ありえない** ．guard がそこだけ無効化されている．

## 🔍 なぜ自分で見つけられなかったか

レビュー依頼の時点で，隣接する穴は自分で挙げていた．

> `BASH_PATTERNS` だけ当たって `POWERSHELL_PATTERNS` が typo の場合，
> bash 側の対象があるため gate は成功する．

つまり「片方の glob だけ当たると素通りする」ことは認識していた．
それでも helper には辿り着かなかった．

**穴を「起こりうる入力」として数えていたためである．**
typo は caller 側の事情であり，こちらから見れば確率の問題に見える．
そこで思考が止まり，「限界として受け入れるか」という問いへ移した．

見落としたのは，**配った物が自分でその入力を作る** という筋である．
確率ではなく既定の状態だった．
「caller が間違えたら」ではなく「こちらが配ったから」である．

指摘の言い回しが違いを言い当てている．
`Exclude the analyzer helper from the target-presence guard` であった．
caller の書き方ではなく，判定の根拠の取り方を問題にしている．

## 📏 同じ形がもう 1 つあった

同じレビューで，repo root の決め方も指摘された．
`Path(__file__).resolve().parents[1]` で決めていた．

`verify-script` input は `.github/scripts/verify-shell.py` のような
深い場所も指せる．そこへ置くと `.github` が root になる．

ここでも「root がずれれば対象 0 件になり，guard が拾う」と考えていた．
実際は `.github/scripts/` に `.sh` があれば `scripts/*.sh` が当たる．
**一部だけを検査して緑になる．**
検査したつもりの範囲と実際の範囲が食い違う分，0 件で落ちるより悪い．

どちらも「guard があるから大丈夫」で思考を止めた点が同じである．
**guard の効き目は，判定へ渡す値が正しいことに依存する．**
guard の有無だけを見て安心すると，値の側が抜ける．

## 🧭 配布物を足すときに見る

配布物は caller の環境で，中央とは違う形で存在する．
足すときは次を確かめる．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. 配布物を足すときの確認項目

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 確認する点 | 今回の当たり方 |
|---|---|
| 自分の検査対象の glob へ入るか | helper が `bin/*.ps1` へ入る |
| 入るなら，判定の根拠から外すべきか | 有無の判定からは外し，解析には残す |
| 置き場所を前提にした計算があるか | repo root を親の階数で決めていた |
| 置かない caller が壊れないか | helper を置くと `pwsh` が必須になる |

最後の 1 つは文書の側にも出た．
「PowerShell 資産を持つ repo だけ」とコメントへ書きながら，
同じコードブロックへ入れていた．貼って実行すれば必ず配置される．
**注意書きは手順にならない．** 実行単位で分ける必要がある．

判定から外す対象は，定数として持つ値と同じものを使う．
今回は `ANALYZER_RELATIVE_PATH` を除外条件へそのまま使った．
caller が置き場所を変えても除外が追随する．

## 📚 参照

- PR #221（`v2.22.0`），Issue #149・#150
- 契約は [docs/shell-quality.md](../shell-quality.md)「雛形から始める」節
- 同じ症状の別系統は
  [2026-09-04-issue184-185-gate-coverage.md](2026-09-04-issue184-185-gate-coverage.md)
- 検査の道具を問いへ合わせる話は
  [2026-09-07-issue211-uses-detection.md](2026-09-07-issue211-uses-detection.md)
