# prh `ユーザ → ユーザー` ルールへの否定先読み追加（Issue #33）

## 背景

`tomio2480/settings` PR #37 のレビューで誤検出が表面化した．
CLAUDE.md 内の正しい表記 `ユーザー` に対して prh が `ユーザ → ユーザー` を 8 件指摘した．
prh は plain string パターンを substring match で扱う．
`ユーザ` を裸で書くと正しい `ユーザー` 内の `ユーザ` 部分にもヒットする．
本リポジトリの `templates/prh.yml` を継承する全 caller で同じ誤検出が起こりうる．

JavaScript ルールの `JS` を裸で書くと `JSON` 等に誤マッチする問題と同根である．
`/\bJS\b/` で word boundary を付けて回避した先例（[docs/rule-rationale.md](../rule-rationale.md) の prh 節）に倣う方針とする．

## 判断

`patterns` を `/ユーザ(?!ー)/` の否定先読み 1 本に置き換える．
plain string `ユーザ` は削除する．

`specs:` には次の 2 件を配置する．

- 正例：`ユーザ登録 → ユーザー登録`（変換が走ること）
- 境界例：`ユーザー登録 → ユーザー登録`（変換されないこと）

prh の `from === to` spec は「変換されないことの自己テスト」として機能する．
否定先読みの効きを YAML 内に閉じ込めて回帰検出する目的．

回帰の二重化は Issue #15 stage 2 と同じ構成とする．

- prh 内 specs：rule 自身の動作を保証
- pytest（`tests/python/test_templates_prh.py`）：YAML 構造を検出．裸の `ユーザ` 不在・否定先読み regex の存在・specs 充足の 3 観点

リリース判定は v2.5.1 patch（既存ルールの誤検出修正のみで構造変更なし）とする．
mutable tag `v2` は最新 patch へ進める．`v1` は self-detection bug により動かさない方針を維持する．

## 代替案と棄却理由

1. **caller 側で `.textlint-allowlist.yml` で吸収**
   個別 caller ごとに「ユーザー」を allowlist 登録する形式．
   中央テンプレを継承する全 caller に同じ作業を強いるため棄却．
   中央側の誤検出は中央側で直すのが本筋．

2. **`expected: ユーザー` ルールごと削除**
   表記ゆれ統一の意図そのものを失う．
   `ユーザ` 単独は依然として指摘したいため棄却．

3. **plain string 2 個（`ユーザ` 単独・`ユーザを` のような助詞付き複合）への分割**
   日本語の活用形を網羅する負担が大きい．
   否定先読みなら 1 本で済むため棄却．

4. **prh 上流（[prh/prh](https://github.com/prh/prh)）に substring match 抑制オプションを提案**
   実装と上流マージの時間がかかり短期解決にならない．
   現行 prh で否定先読みが機能するため当面は中央テンプレ側で対処する．

## 参照

- [Issue #33](https://github.com/tomio2480/github-workflows/issues/33) — 問題の発端と実装方針コメント
- [tomio2480/settings PR #37](https://github.com/tomio2480/settings/pull/37) — 誤検出 8 件を観測した PR
- [docs/rule-rationale.md](../rule-rationale.md) — `JS` 裸書きの substring match 回避の先例
- [PR #23](https://github.com/tomio2480/github-workflows/pull/23) — Issue #15 stage 2．specs と pytest の二重回帰の先例
- [prh README](https://github.com/prh/prh) — specs 仕様
