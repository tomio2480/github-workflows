# Issue #117〜#119 対応の知見（markdownlint 実行経路の一本化）

## 要約

markdown-lint composite action の 3 連 Issue（#117・#118・#119）を
連続対応した際の設計判断と学びを記録する．markdownlint の実行を
`markdownlint-cli2` の 1 回へ一本化し（v2.11.0），診断ログを足し
（v2.11.1），summary へ検査対象 base を併記した（v2.12.0）．

## 目次

- 背景
- 判断
- 代替案と棄却理由
- 詰まった箇所と解決
- レビューでの学び
- 残課題
- 参照

## 背景

caller 実測で，reviewdog 経路（`markdownlint-cli` v0.41.0）と
summary 集計経路（`markdownlint-cli2`）の指摘件数が 870 対 61 で
食い違った（#117）．cli は cli2 形式設定の `config:` / `ignores:` を
解釈しないためである．また summary の全体件数が 0 になっても，
原因をログから切り分けられない事象があった（#118）．全体件数が
古い base 由来で残って見える混乱も caller で起きていた（#119）．

## 判断

- **実行系は cli2 の 1 回へ統一する．** 集計用に走っていた cli2 の
  結果テキストを errorformat（列あり・列なしの 2 つの `-efm`）で
  reviewdog CLI へ渡す．設定解釈の不一致を構造ごと除去した．
- **実行失敗はフェイルクローズにする．** cli2 は指摘ありで exit 1 を
  返すが，npm/npx の実行失敗も exit 1 を返しうる．そこで起動成功時に
  必ず出る banner 行の有無を併用し，「exit 1 かつ banner あり」だけを
  正常系とした．lint 指摘では失敗させず，実行エラーは失敗させるという
  action 既存契約（`fail-on-error` input の説明）に揃えた．
- **切り分けはログで足す．** レポート行数と `Linting:`（走査ファイル数）
  `Summary:`（件数）の行をステップログへ写す．形式が変われば
  `::warning::` 自体が検知信号になる．
- **summary へ検査対象 base を併記する．** 全体件数は checkout した
  マージコミットの base 時点の値であり，main の現在値ではない．
  base を明示して summary 単体で時差を判別できるようにした．

## 代替案と棄却理由

- cli 用 config を cli2 設定から生成して併設する案: 設定の二重管理に
  なるため棄却．実行系の統一が本質的な解と判断した．
- 実行失敗判定を「レポートが空か」で行う案（textlint ステップと同方式）:
  cli2 は banner を必ず出すためレポートが空にならず，流用できない．
  banner 行の有無という cli2 固有の判定に切り替えた．
- 診断分岐の `scripts/` 抽出＋bats 化: 純粋なログ写しであり，
  textlint ステップの同種判定もインラインである現状に揃えた．

## 詰まった箇所と解決

- **遡及調査の限界．** 全出力を `> report.txt 2>&1 || true` で落とす
  設計では，caller run のログに証跡が一切残らない．該当 run のログを
  取得しても count ステップは約 4.2 秒・出力ゼロで，原因は確定できず，
  診断ログの追加という予防で対応した．
- **副次発見．** 同じ run で，撤去前の `reviewdog/action-markdownlint`
  は markdownlint-cli の引数解釈に失敗して usage を出力していた．
  つまり inline 投稿経路は実は機能していなかった．870 件という数字は
  Issue 起票者のローカル再現値であり，CI 上の実挙動ではなかった．
  Issue の前提も一次ログで裏取りする価値を再確認した．

## レビューでの学び

- Codex P1: `|| true` は実行失敗まで成功へ変換する．経路を一本化して
  レポートが唯一の生成元になった時点で，握りつぶしの深刻度が上がる．
  依存を減らす変更は，残った経路の失敗モードを見直す契機になる．
- セキュリティレビュー: SHA pin 済み action の撤去により，実行部が
  floating semver の `npx` だけになった（#121 へ切り出し）．
  露出面が「増えていない」ことと「残った経路の格が下がる」ことは別．
- Codex P2: caller config の `outputFormatters` は既定 formatter を
  置き換える（cli2 実装で裏取り済み）．既定出力形式への依存は
  従来からあり，新規リグレッションではないと整理して #122 へ切り出した．

## 残課題

- #121: markdownlint-cli2 の lockfile 管理化（Dependabot 追随）．
- #122: `outputFormatters` の runtime config サニタイズ．
- 本リポジトリの textlint 全体件数に 1 件の残存がある．PR #124 の
  summary で観測した．対象ファイルは未特定．

## 参照

- Issue: [#117](https://github.com/tomio2480/github-workflows/issues/117)
  / [#118](https://github.com/tomio2480/github-workflows/issues/118)
  / [#119](https://github.com/tomio2480/github-workflows/issues/119)
- PR: [#120](https://github.com/tomio2480/github-workflows/pull/120)
  / [#123](https://github.com/tomio2480/github-workflows/pull/123)
  / [#124](https://github.com/tomio2480/github-workflows/pull/124)
- リリース: v2.11.0 / v2.11.1 / v2.12.0
- 派生 Issue: [#121](https://github.com/tomio2480/github-workflows/issues/121)
  / [#122](https://github.com/tomio2480/github-workflows/issues/122)
