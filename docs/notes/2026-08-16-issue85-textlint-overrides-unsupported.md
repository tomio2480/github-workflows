# textlint の overrides は未実装であり per-path 文体切り替えに使えない

## 要約

`.textlintrc.json` の `overrides` による per-path 文体切り替えは動作しない．
textlint 15.6.0 が `overrides` を実装していないためである．
中央テンプレートの `_example_overrides` と `docs/rule-rationale.md` の案内を撤去した．
`generate-textlint-runtime.py` の `overrides` 解決経路は「素通し + 警告」へ改めた．
代替の既定はファイル先頭の `<!-- textlint-disable -->` コメントとする．
`.textlintignore` は lint 対象外にしたいファイル限定の手段とする．

## 目次

- 背景
- 判断
- 代替案と棄却理由
- 検証で見落とした要因
- 波及先
- 参照

## 背景

`tomio2480/techbook-template` で `src/chapters/**` を `overrides` でですます調と宣言した．
手元実行すると `no-mix-dearu-desumasu` が 16 件出た．
最小構成で再現し，`node_modules` 配下の textlint 本体を横断検索した．
`overrides` の文字列は 1 件も無かった．
本セッションでも同じ横断検索を手元で再実行し，0 件であることを裏取りした．

## 判断

- `docs/rule-rationale.md` の「方法 A: overrides」を「使えない方法」節へ移した．
  動作しない理由と，CI の緑が動作確認にならなかった経緯を残す．
- 方法 A の座には，ファイル先頭コメントによる当該ルール無効化を置く．
  中央テンプレートが `filters.comments: true` を持つため追加設定なしで効く．
- `templates/.textlintrc.json` から `_example_overrides` を削除する．
- `generate-textlint-runtime.py` の `overrides[*].rules.prh` 解決処理は撤去する．
  `overrides` が非空なら `::warning::` アノテーションを出し，中身は書き換えない．
  型検査で落とす選択は採らない．
  caller の CI を突然壊すより，効いていない事実を警告で見せる方が移行しやすい．

## 代替案と棄却理由

- `overrides` 経路をコードへ残す案: textlint 側に実装が無く死んだ経路である．
  テストだけが通り続ける状態は誤解の温床になるため撤去した．
- 文体だけ違う設定ファイルを別に置き，caller 側で 2 回走らせる案:
  composite action の inputs 設計変更を伴う．
  本 Issue の範囲を超えるため，需要が観測されたら別 Issue とする．
- `.textlintignore` を既定の代替にする案: 文体以外の検査まで落ちる．
  文長・助詞重複・表記ゆれが対象外になるため，既定にしない．

## 検証で見落とした要因

`tomio2480/settings` PR #48 は「CI が通れば動作確認できる」を検証観点にしていた．
composite action の既定は `filter-mode: added`・`fail-on-error: false` である．
差分行以外の指摘は表に出ず，指摘があっても job は失敗しない．
そのため「効いていない設定」と「効いている設定」が CI 上で区別できなかった．
設定変更の動作確認は，手元で `npx textlint` を直接実行して行う．
または `filter-mode: nofilter` を一時的に指定し，全指摘を表示させて行う．

## 波及先

- `tomio2480/settings`: グローバル `CLAUDE.md` の「ディレクトリ単位で変えるとき」節が
  `overrides` を案内している．同リポジトリで修正 Issue を起票する．
- `tomio2480/techbook-template`: `src/chapters/**` の `overrides` 宣言が無効である．
  同リポジトリへ連絡し，コメント方式か `.textlintignore` へ移行する．

## 参照

- [Issue #85](https://github.com/tomio2480/github-workflows/issues/85)（本件）
- [Issue #22](https://github.com/tomio2480/github-workflows/issues/22)（元の提案）
- `tomio2480/settings` PR #48（検証を試みた PR）
- `tomio2480/techbook-template` #98（発見元）
- [docs/rule-rationale.md](../rule-rationale.md) の「文体使い分けと no-mix-dearu-desumasu」節
