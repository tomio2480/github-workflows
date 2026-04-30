# 全角記号前後の半角スペース検出ルールの追加（Issue #15 stage 2）

## 背景

caller 原稿（blog-private 等）で Gemini Code Assist が繰り返し指摘してきた JTF 逸脱パターンがある．
中央 prh ルールでこれを機械検出可能にする取り組みである．
対象は中黒 `・`・全角スラッシュ `／`・全角コロン `：`・波ダッシュ `〜` の 4 シンボルである．
これらの前後に半角スペースが入っているケースを検出する．

stage 1（PR #21）で fixture 化し，stage 2 で中央 prh ルールとして追加した．
新規 npm 依存なしで実現できる既存 prh の拡張として位置づけた．

## 判断

prh の長い順 alternation `/ X | X|X /` を 1 本書く方式を採用した．
1 シンボルにつき 1 rule を定義し，`specs:` に両側・前のみ・後のみの 3 件を配置する．
動作の担保は YAML 内 specs と pytest の二重で行う．
specs は prh 自身が保証する自己テストで，pytest は YAML の構造（rule 存在・正規表現形式・specs 充足）を回帰検出する．

リリース判定は v2.2 patch（追加検出のみで構造変更なし）とした．
mutable tag（`v1`/`v2`）は動かさない．

## 代替案と棄却理由

1. **独自 textlint rule 新設**
   npm package の追加・自作・publish のコストが大きい．
   既存 prh で実現可能なため棄却した．

2. **`markdownlint-cli2` のカスタム regex rule**
   本リポジトリは Markdown と textlint を分離管理している．
   日本語表記の検出は textlint 側に寄せる方針であり，
   `markdownlint-cli2` 側にカスタムルールの先例もないため棄却した．

3. **同一 rule 内の 2 pattern 分離**
   `[/ X/, /X /]` のように leading/trailing を分割する書き方である．
   prh 内部で `/(?: X|X )/gmu` に合成され，両側スペース入力で後続スペースを取りこぼす．
   spec が落ちることを確認し，長い順 alternation 1 本に統一して棄却した．

4. **8 個の独立 rule（leading/trailing × 4 シンボル）**
   spec が分散し YAML が冗長になる．
   lint 時に 2 件 flag が出ることを諦めれば 4 rule で済むため，
   4 rule の長い順 alternation に統一して棄却した．

## 参照

- [Issue #15](https://github.com/tomio2480/github-workflows/issues/15) — 問題の発端と採用方針の議論
- [PR #21](https://github.com/tomio2480/github-workflows/pull/21) — stage 1: fixture 追加
- [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf) — 全角記号周りのスペース規定
- [prh README](https://github.com/prh/prh) — specs 仕様と pattern の合成ロジック
