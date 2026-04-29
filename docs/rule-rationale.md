# 📐 採用ルールの根拠

## 要約

本リポジトリの textlint ルールセットは [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf) を基準に選定している．
中央 caller 横断で表記の一貫性を担保しつつ，per-repo override で個別事情を吸収できる構成にしている．
ここでは利用者から問い合わせを受けやすい `ja-no-space-around-parentheses` を例に，主要ルールの採用根拠を整理する．

## 目次

- 🎯 採用方針
- 🧩 ja-no-space-around-parentheses の根拠
- 📦 prh の表記ゆれ辞書
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

辞書追加の手順は [docs/dictionary-maintenance.md](dictionary-maintenance.md) を参照．

## 📚 参照

- [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf)
- [textlint-rule-preset-ja-spacing](https://github.com/textlint-ja/textlint-rule-preset-ja-spacing)
- [textlint-rule-preset-ja-technical-writing](https://github.com/textlint-ja/textlint-rule-preset-ja-technical-writing)
- [textlint-rule-preset-JTF-style](https://github.com/textlint-ja/textlint-rule-preset-JTF-style)
