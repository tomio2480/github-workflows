# MD036 の方針決定と lint summary 全体件数併記の知見

## 要約

Issue #102・#103・#104 の対応（PR #105・#106・#107）で得た知見を記録する．
規則の挙動を実測してから方針を決めたことで，Issue 起票時の前提が覆り，
設定変更なしの共存策（書き方ルール）に到達した．
summary への全体件数併記は，導入した PR 自身で既存負債の可視化効果を実証した．

## 目次

- 🔍 背景
- 🧭 判断
- 🚫 代替案と棄却理由
- 🧪 検証環境の知見
- 📌 残課題
- 📚 参照

## 🔍 背景

caller の `tomio2480/techbook-template` で全体検査を走らせた．
その結果，PR に一度も現れていない指摘が 125 件見つかった．
内訳は `markdownlint` 30 件・`textlint` 95 件である．
派生した課題が 3 つの Issue に分かれた．
MD036 と全角句点の誤検出（#102），太字小見出しとの共存方針（#103），
summary の全体件数併記（#104）である．

## 🧭 判断

### 実測が方針を変えた（#103）

MD036 の発火条件を fixture で実測した結果，発火は
「太字だけの 1 行段落（句読点で終わらない）」に限られると判明した．
Issue 本文の例（`**半値角** 説明文…` の同一行形式）は実は検出されない．
このため設定変更（中央無効化・override 案内）を選ばず，
「ラベルと本文の段落を分離しない」書き方ルールで共存する案 4 を採用した．
実測表と推奨する書き方は `docs/rule-rationale.md` の MD036 節へ明文化した．

### 全体件数は再集計のみで併記する（#104）

`markdownlint-report.txt` と `textlint-report.xml` は元々全体走査の結果を持つ．
`count-lint-findings.py` へ `repo_total` と `diff_scoped` を追加した．
`repo_total` は diff 絞り込み前・ignore 適用後の件数である．
検査の追加実行なしで全体件数を summary へ併記できた．
旧スキーマの payload は従来表示に落とす後方互換とした．
導入 PR #107 自身の summary で「差分 52 件・全体 261 件」が表示され，
狙いどおり既存負債の可視化効果を実証できた．

## 🚫 代替案と棄却理由

- **MD036 の中央無効化（#103 案 1）**: ラベルを使わない caller の検出力まで
  下がるため棄却した．
- **caller override の案内（#103 案 2）**: 中央設定の全置換になり
  Issue #83 の drift を招くため棄却した．
- **`filter-mode: nofilter` の既定化（#104 代替案）**: 差分外の指摘まで
  inline に付くため，可視化の既定としては棄却した．

## 🧪 検証環境の知見

- Codex レビューの `markdownlint-disable` 指摘は妥当だった．
  disable は対応する enable まで効き続けるため，単一例外の案内は
  `disable-next-line` を使う．
- Windows ローカルの bats（npx 経由 1.11.0）は日本語のテスト名を
  扱えず全テストが unknown test name になる．bats の実行は CI へ委ね，
  レンダリングは fake curl を PATH 先頭へ置いた手動実行で検証した．
- prh の `markdown → Markdown` 規則は `markdownlint` の前方部分にも
  マッチする．コマンド名をバッククォートで囲めば回避できる．

## 📌 残課題

- 本リポジトリ自身に textlint 261 件の既存指摘が残ると #107 で判明した．
  解消 Issue の起票要否はユーザー判断待ちである．
- `techbook-template#176` へ v2.8.2〜v2.9.1 の反映を連絡するか未決である．

## 📚 参照

- [Issue #102](https://github.com/tomio2480/github-workflows/issues/102) / [PR #105](https://github.com/tomio2480/github-workflows/pull/105)（v2.8.2）
- [Issue #103](https://github.com/tomio2480/github-workflows/issues/103) / [PR #106](https://github.com/tomio2480/github-workflows/pull/106)（v2.9.1）
- [Issue #104](https://github.com/tomio2480/github-workflows/issues/104) / [PR #107](https://github.com/tomio2480/github-workflows/pull/107)（v2.9.0）
- [docs/rule-rationale.md](../rule-rationale.md) — MD036 と太字の小見出し
- [docs/architecture.md](../architecture.md) — 表 6（summary コメントの仕様）
