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
- 🧩 文体使い分けと no-mix-dearu-desumasu
- 📚 参照

## 🎯 採用方針

中央テンプレに同梱するルールは次の 4 観点で評価する．
ひとつでも満たせば採用候補とし，反証が無ければ既定として有効化する．

- 業界の事実上の標準に整合する
- 日本語組版の慣習に整合する
- 機械処理（screen reader 等）で冗長を生まない
- データの整合性に資する

caller 固有の例外は per-repo override で吸収する前提とし，中央側は「広く効く既定」を優先する方針である．
個別 caller の例外語彙は v2.1（[Issue #14](https://github.com/tomio2480/github-workflows/issues/14) で実装）以降，caller root に `.textlint-allowlist.yml` を置くことで扱える．運用方針は [docs/dictionary-maintenance.md](dictionary-maintenance.md) を参照．

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

`ユーザー` ルールも同根の問題を回避している．
plain string `ユーザ` は正しい表記の `ユーザー` 内の `ユーザ` 部分にも substring match して誤検出する．
否定先読み `/ユーザ(?!ー)/` で「ユーザー」を除外する設計とする（[Issue #33](https://github.com/tomio2480/github-workflows/issues/33)）．

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

### 方法 A: overrides による per-path 切り替え

caller root に `.textlintrc.json` を配置し，`overrides` フィールドを使う．
中央テンプレートの `_example_overrides` キーに使用例を示している．
`_example_overrides` を `overrides` にリネームして有効化する．

```json
{
  "overrides": [
    {
      "files": ["claude/agents/**/*.md"],
      "rules": {
        "preset-ja-technical-writing": {
          "no-mix-dearu-desumasu": {
            "preferInBody": "ですます",
            "preferInList": "ですます",
            "strict": false
          }
        }
      }
    }
  ]
}
```

`overrides` 内に `prh.rulePaths` が含まれる場合も `generate-textlint-runtime.py`
が絶対パスへ解決する．`prh.yml` を caller 側に配置しなければ中央テンプレートが自動採用される．

**注意** ：textlint v14 では `overrides` で preset 由来ルールを上書きすると
解釈エラーを起こす事例が報告されている（Issue #22）．textlint v15 での動作は
本リポジトリでは未検証のため，動作しない場合は方法 B を使うこと．
検証完了後，本節を更新予定．

### 方法 B: .textlintignore による除外

対象ファイルを textlint チェックから外す方法で，動作が確実である．

```text
# .textlintignore
claude/agents/
```

ファイル全体が対象外になるため，文体以外のルール（表記ゆれ・助詞重複など）も
チェックされなくなる点に注意する．

## 📚 参照

- [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf)
- [textlint-rule-preset-ja-spacing](https://github.com/textlint-ja/textlint-rule-preset-ja-spacing)
- [textlint-rule-preset-ja-technical-writing](https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing)
- [textlint-rule-preset-JTF-style](https://github.com/textlint-ja/textlint-rule-preset-JTF-style)
