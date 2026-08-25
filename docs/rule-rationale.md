# 📐 採用ルールの根拠

## 要約

本リポジトリの textlint ルールセットは [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf) を基準に選定している．
中央 caller 横断で表記の一貫性を担保しつつ，per-repo override で個別事情を吸収できる構成にしている．
ここでは利用者から問い合わせを受けやすい `ja-no-space-around-parentheses` を例に，主要ルールの採用根拠を整理する．

## 目次

- 🎯 採用方針
- 🧩 ja-no-space-around-parentheses の根拠
- 📦 prh の表記ゆれ辞書
- 🧩 全角記号前後の半角スペース禁止の根拠
- 🧩 LLM 定型句の抑制
- 🧩 文体使い分けと no-mix-dearu-desumasu
- 🧩 max-kanji-continuous-len と固有名詞の例外
- 🧩 sentence-length の skipPatterns
- 📚 参照

## 🎯 採用方針

中央テンプレに同梱するルールは次の 4 観点で評価する．
ひとつでも満たせば採用候補とし，反証が無ければ既定として有効化する．

- 業界の事実上の標準に整合する
- 日本語組版の慣習に整合する
- 機械処理（screen reader 等）で冗長を生まない
- データの整合性に資する

caller 固有の例外は per-repo override で吸収する前提とし，中央側は「広く効く既定」を優先する方針である．
個別 caller の例外語彙は v2.1 以降，caller root の `.textlint-allowlist.yml` で扱える．
実装経緯は [Issue #14](https://github.com/tomio2480/github-workflows/issues/14) を参照．
caller 固有の表記ゆれ規則（読点の流儀など）は v2.7 以降，caller root の `.prh-extra.yml` で中央辞書へ加算できる．
実装経緯は [Issue #91](https://github.com/tomio2480/github-workflows/issues/91) を参照．
中央辞書に入れるか caller 追加辞書に置くかは「全 caller に効く既定として妥当か」で決める．
運用方針は [docs/dictionary-maintenance.md](dictionary-maintenance.md) を参照．

## 🧩 ja-no-space-around-parentheses の根拠

全角カッコ `（）` と鉤カッコ `「」` の **前後** に半角スペースを入れない設定としている．
根拠は表 1 のとおり．強度の高い順に並べている．

表 1: ja-no-space-around-parentheses の採用根拠（強度の高い順）

| 観点 | 内容 | 出典 |
|---|---|---|
| 業界慣習 | JTF 日本語標準スタイルガイドが全角カッコの内外スペース禁止を規定．preset-ja-spacing も同方針を踏襲 | [textlint-rule-preset-JTF-style](https://github.com/textlint-ja/textlint-rule-preset-JTF-style) |
| 日本語組版 | 全角カッコは前後の文字幅に合わせて字面を縮める前提で設計されている．半角スペースを入れると本来不要な余白が二重化する | [textlint-rule-preset-ja-spacing](https://github.com/textlint-ja/textlint-rule-preset-ja-spacing) |
| アクセシビリティ | 多くの screen reader は記号を文字として読み上げる．冗長スペースが冗長読み上げを誘発する実装もある | [Deque: Screen Readers and Punctuation](https://www.deque.com/blog/dont-screen-readers-read-whats-screen-part-1-punctuation-typographic-symbols/) |
| データ整合性 | 1 スペース = 1 バイト UTF-8．影響は軽微だが「無し」で揃えたほうが一貫性が高い | （業界慣習） |

## 📦 prh の表記ゆれ辞書

`templates/prh.yml` の `JavaScript` ルールでは `JS` を `/\bJS\b/` の正規表現で検出する．
plain string で `JS` と書くと substring match が効き，`JSON Lines` のような語にも誤マッチするため避ける．

`ユーザー`・`サーバー`・`コンピューター` ルールも同根の問題を回避している．
長音「ー」で終わる語を plain string で書くと，正しい表記（例: `サーバー`）内の
部分文字列（例: `サーバ`）にも substring match して誤検出する．
否定先読み `(?!ー)` で長音が続く場合を除外する設計で統一する
（[Issue #33](https://github.com/tomio2480/github-workflows/issues/33)・[Issue #48](https://github.com/tomio2480/github-workflows/issues/48)）．

辞書追加の手順は [docs/dictionary-maintenance.md](dictionary-maintenance.md) を参照．

## 🧩 全角記号前後の半角スペース禁止の根拠

4 シンボル（中黒 `・`・全角スラッシュ `／`・全角コロン `：`・波ダッシュ `〜`）を対象に，
前後の半角スペースを禁止するルールを追加している．
JTF 日本語標準スタイルガイドの全角記号周りの規定に準拠した対応である．

根拠は表 2 のとおり．強度の高い順に並べている．

表 2: 全角記号前後の半角スペース禁止の採用根拠（強度の高い順）

| 観点 | 内容 | 出典 |
|---|---|---|
| 業界慣習 | JTF 日本語標準スタイルガイドが全角句読点・記号後スペース禁止を規定．Gemini Code Assist が caller 原稿で繰り返し指摘してきた事象（[Issue #15](https://github.com/tomio2480/github-workflows/issues/15)）と合致 | [JTF スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf) |
| 日本語組版 | 全角記号は前後の文字幅に合わせて字面を縮める前提で設計されている．半角スペース挿入は組版上の冗長な余白を生む | [textlint-rule-preset-ja-spacing](https://github.com/textlint-ja/textlint-rule-preset-ja-spacing) |
| アクセシビリティ | screen reader が記号と前後文字を別語として読み上げ，冗長読み上げを誘発する実装がある | [Deque: Screen Readers and Punctuation](https://www.deque.com/blog/dont-screen-readers-read-whats-screen-part-1-punctuation-typographic-symbols/) |
| データ整合性 | 機械処理（diff・grep・置換）で表記ゆれが残ると整合性検査が困難になる．preset-ja-spacing で機械検出できなかった範囲を prh で補う | （業界慣習） |

patterns 設計について補足する．
prh は同一 rule 内の複数 pattern を alternation に合成する．
leading/trailing を別 pattern に分割すると後続の取りこぼしが発生する．
そのため `/ +X +| +X|X +/` の長い順 alternation 1 本で leftmost-longest を機能させている．量指定子 `+` でシングル・ダブルスペース等の typo を一括して扱う．

caller が `--fix` を組み込む場合は事前に diff 確認を推奨する．
中央 composite action は `--fix` を起動しない．
caller 独自パイプラインで有効化すると一括置換が走るため，事前のレビューが必要になる．

per-repo の例外は caller root に `.textlint-allowlist.yml` を置くことで吸収できる（v2.1 以降）．
詳細は [docs/dictionary-maintenance.md](dictionary-maintenance.md) の「prh と caller-side allowlist の使い分け」を参照．

## 🧩 LLM 定型句の抑制

LLM が生成しがちな空虚な定型表現を prh で検出する
（[Issue #54](https://github.com/tomio2480/github-workflows/issues/54)）．
出典は [k16shikano 氏の Gist](https://gist.github.com/k16shikano/fd287c3133457c4fd8f5601d34aa817d) である．
検出結果は既定で warning レベルの advisory であり，job を失敗させない．

### 収録基準

識別性が高く，技術文書での正当な用法が少ない語句に限定する．
v1 は次の 7 語を収録する．

- `重要なのは`
- `正面から`（定型動詞に限定）
- `不可欠`（`必要不可欠` を含む）
- `核心的`
- `掘り下げ`
- `深掘り`
- `に他ならない`（ひらがな表記 `にほかならない` を含む）

過剰マッチ抑制のための pattern 設計は次のとおり．

- `正面から` は物理的・字義的な用法（例: `正面から見た図`）を誤検出しないよう，
  定型句で使われる動詞（扱う・向き合う・取り組む・回収する）に限定する．
- `不可欠` は `必要不可欠` を長一致で先に検出し，二重置換と重複検出を
  否定戻り読みで防ぐ（`ユーザー` ルール等と同系の設計）．

### 除外した候補と理由

出典 Gist の候補のうち，次は技術文書での正当な用法が多く v1 では見送る．

- `言及する`・`触れる`：参照記述（例: Issue で言及した）として頻出する．
- `〜において`・`〜の観点から`：条件・視点の明示として正当な用法が多い．
- `包括的`・`総合的`・`根本的`・`多角的`：修飾対象が具体的なら正当である．
- `まとめると`・`要するに`：要約の導入として正当な用法がある．
- `非常に`・`極めて`：一般語で過剰マッチが大きい．

再検討する場合は，caller 横断で指摘が繰り返される実績を根拠とする．

### expected の性質と --fix の注意

機械置換できる 2 語（`不可欠` → `必要`，`に他ならない` → `である`）を除き，
expected は（）付きのガイダンス文字列である．自動置換には適さない．
中央 composite action は `--fix` を起動せず，CI 経路（checkstyle → reviewdog）では
fix 情報を使わないため影響はない．
caller 独自パイプラインで `--fix` を有効化する場合は本節ルールの diff 確認が必要になる．

per-repo の例外は `.textlint-allowlist.yml` で吸収できる（v2.1 以降）．

## 🧩 文体使い分けと no-mix-dearu-desumasu

中央テンプレートの `no-mix-dearu-desumasu` 既定設定を表 3 に示す．

表 3: no-mix-dearu-desumasu の既定設定．

| フィールド | 既定値 | 意味 |
|---|---|---|
| `preferInBody` | `"である"` | 本文はである調を優先する |
| `preferInList` | `"である"` | リスト項目もである調を優先する |
| `preferInHeader` | `""` | 見出しは文体を制約しない |
| `strict` | `false` | 混在検出を厳密にしない |

指示書ファイル（ですます調）と規律文書（である調）が同一 repo に共存する場合，
以下 2 つの方法でファイル種別ごとに文体を切り替えられる．
範囲の狭い方法 A を既定とする．

### 方法 A: ファイル先頭コメントによる当該ルールの無効化

対象ファイルの先頭に次の 2 行を置く．無効化の理由もコメントで残す．

```markdown
<!-- 本ファイルは指示書のため「ですます調」で書く．この 1 ルールだけ無効化する． -->
<!-- textlint-disable ja-technical-writing/no-mix-dearu-desumasu -->
```

中央テンプレートは `filters.comments: true` を有効にしているため，
この方法が caller 側の追加設定なしで使える．
文長・助詞重複・表記ゆれの検査は効いたまま残る．

### 方法 B: .textlintignore による除外

対象ファイルを textlint チェックから外す方法で，動作が確実である．

```text
# .textlintignore
claude/agents/
```

ファイル全体が対象外になるため，文体以外のルール（表記ゆれ・助詞重複など）も
チェックされなくなる点に注意する．
生成物・外部由来ファイル・英語コンテンツなど，lint 対象外としたいものへ限って使う．
文体だけを理由に選ばない．

### 使えない方法: overrides による per-path 切り替え

`.textlintrc.json` の `overrides` キーは ESLint 風の per-path 設定である．
textlint 15.6.0 時点では **本体が実装していない機能** である．
`@textlint/config-loader` が読むのは `plugins`・`filters`・`rules` の 3 キーのみ．
`overrides` は無視される．
経緯は [Issue #85](https://github.com/tomio2480/github-workflows/issues/85) を参照．

かつて本節と中央テンプレートの `_example_overrides` はこの方法を案内していた．
「動作を確認した」とした根拠は CI が緑になったことだった．
しかし composite action の既定は `filter-mode: added`・`fail-on-error: false` である．
差分行以外の指摘は表に出ず，指摘があっても job は失敗しない．
そのため CI の緑は動作確認にならなかった．
文体設定の動作確認は，手元で `npx textlint` を直接実行して行う．
または `filter-mode: nofilter` を一時的に指定し，全指摘を表示させて行う．

`overrides` を含む `.textlintrc.json` を渡した場合の挙動は次のとおり．
`generate-textlint-runtime.py` は中身を書き換えず素通しする．
あわせて Actions ログへ `::warning::` アノテーションで効いていない旨を出す．
textlint 本体に `overrides` が実装された時点で本節を見直す．

## 🧩 max-kanji-continuous-len と固有名詞の例外

`max-kanji-continuous-len` は漢字が連続する文字数を制限するルールで，既定値は `max: 6` である．
固有名詞など，意味を損なわずに分割できない語が誤検出される場合がある．
`allow` オプションで例外を文字列配列として指定することで回避できる
（[Issue #49](https://github.com/tomio2480/github-workflows/issues/49)）．

```json
{
  "rules": {
    "preset-ja-technical-writing": {
      "max-kanji-continuous-len": {
        "max": 6,
        "allow": ["電子情報通信学会", "情報処理推進機構"]
      }
    }
  }
}
```

中央テンプレートは `"allow": []`（空リスト）を既定として定義する．
固有名詞の例外は各 caller リポジトリで per-repo の `.textlintrc.json` に追加する運用とする．
caller-side の除外方針については
[docs/dictionary-maintenance.md](dictionary-maintenance.md) の「5️⃣」節も参照する．

## 🧩 sentence-length の skipPatterns

`sentence-length`（`max: 80`）は，読み上げに現れない記法の字数まで数える．
数式を多く含む原稿では，見かけが 80 字未満の文が大量に誤検出される．
このため `skipPatterns` でインライン数式 `$…$` を文長から外す
（[Issue #96](https://github.com/tomio2480/github-workflows/issues/96)）．

```json
"sentence-length": {
  "max": 80,
  "skipPatterns": [
    "/\\$[^$]*\\$/"
  ]
}
```

適用先リポジトリでの実測では，`sentence-length` の指摘 12 件のうち
11 件は記法を除けば 80 字未満だった．詳細は Issue #96 を参照．

Issue #96 は索引アンカー `<a id="…"></a>` のパターンも提案していたが，採用しない．
中央がピンする `textlint-util-to-string` は inline HTML ノードを文字列化から落とす．
アンカーはもともと文長に数えられておらず，パターンは常に不発になる（本リポジトリで実測）．
`skipPatterns` は文字列化後のテキストに対して働くため，HTML はそこに現れない．
効かない設定を残すと「アンカーが数えられている」という誤解を招くため外した．

脚注 `^[…]` も `skipPatterns` では消せない．`sentence-splitter` が
`[ ]` の中を 1 文として扱い，パターンが文の内側に収まらないためである．
インライン脚注は参照形式（`[^name]` と定義行）への書き換えで対処する（原稿側の課題）．

## 📚 参照

- [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf)
- [textlint-rule-preset-ja-spacing](https://github.com/textlint-ja/textlint-rule-preset-ja-spacing)
- [textlint-rule-preset-ja-technical-writing](https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing)
- [textlint-rule-preset-JTF-style](https://github.com/textlint-ja/textlint-rule-preset-JTF-style)
