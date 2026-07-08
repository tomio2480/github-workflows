# キャプション体言止めと ja-no-mixed-period の衝突（Issue #57）

## 要約

Issue #57 で提起された「箇条書き・キャプションでの `ja-no-mixed-period`
誤検出」について，実証テストと影響範囲を確認した．
箇条書きは仕様上除外済みで誤検出しないが，独立した図表キャプションの
段落は句点必須のまま検出対象であることを確認した．
現行 caller には実害がないため，中央テンプレートの変更は行わず，
設計判断のみを記録して Issue はオープン継続とする．

## 目次

- 実証テストの結果
- 発端となった techbook 側の実情
- 現行 caller への影響確認
- 判断
- 見直しトリガ

---

## 実証テストの結果

`templates/.textlintrc.json` を用いた．
次の 3 種の文末なし表現を含む Markdown fixture に対し，
`textlint` を実行した．

- 箇条書き項目（体言止め，句点なし）
- 独立した図キャプション段落（例：`図 3.5.-1 led-circuit.svg を清書版に差し替え`）
- 表キャプション段落（例：`表 1. サンプルの表`）

結果は次のとおりである．

- 箇条書き項目：検出されない．`ListItem` が既定で除外対象のため．
- 図キャプション段落：`ja-no-mixed-period` に検出される．
- 表キャプション段落：`ja-no-mixed-period` に検出される．

Issue #57 のコメントで示された仮説（誤検出の実体は箇条書きではなく
キャプション）が実証テストで裏付けられた．

## 発端となった techbook 側の実情

発端の
[techbook-introduction-to-electronics-basic-led#3](https://github.com/tomio2480/techbook-introduction-to-electronics-basic-led/issues/3)
を確認したところ，次の事実があった．

- 同リポジトリには `.textlintrc.json` や lint 用ワークフローが存在せず，
  本リポジトリの中央設定を一切使っていない．
- 「誤検出」は実際の lint 実行結果ではなく，人手校閲（Claude によるレビュー）
  で「本書の体言止め慣例と一般規律が食い違う」と気づいたものだった．
- 同 Issue 内の議論で，最終的に「現状維持（句点なしの体言止め）」で
  決着している．

つまり本件は実際の誤検出事例ではない．
将来同種の文書が中央設定を採用した場合に備える，
予防的な設計検討という位置づけになる．

## 現行 caller への影響確認

本リポジトリの中央 lint 設定（`md-lint.yml`）を実際に参照している
caller を横断的に確認した．

- `blog-pipeline` / `blog-private` / `chrome-tab-tidy-up` /
  `frontend-phpcon-do-2026` / `keiba-form-chart` / `picoruby-tea5767` /
  `settings`

いずれもユーザーのグローバル規律（`CLAUDE.md` の「文末は『．』で統一する．
箇条書き・キャプションも同様．」）に沿って作成された文書である．
図表キャプションにも句点を付与する慣例が既に定着しており，
サンプル検索でも句点付きキャプションの使用を確認した．
現時点で本件により実害を受けている caller はない．

## 判断

- 中央テンプレート（`templates/.textlintrc.json`・`docs/rule-rationale.md`）
  の変更は行わない．
  実害のある caller が存在しない状況での先回り対応は
  過剰設計（YAGNI 違反）と判断した．
- 案 B（AST ノード種別ベースの `overrides`）は textlint 本体の機構上
  実現不可能である．
  Issue #57 の調査で確認済みであり，再検討の余地はない．
- 案 C（caller 側 `.textlintrc.json` でのファイル単位無効化）は，
  該当 caller が現れた時点で対応する．
  体言止めキャプションを採用したい要望が対象になる．
  その際は `docs/dictionary-maintenance.md` に手順を追記する．
- Issue #57 は Issue #15 と同様に「経緯の保管庫」としてオープン継続する．

## 見直しトリガ

以下のいずれかが観測された場合，Issue #57 で再度判断する．

- 本リポジトリの中央設定を採用する caller が，句点なしの体言止め
  キャプションを規約として持ち込みたいと要望したとき．
- techbook 側が将来 lint 導入を検討したとき．
  実際に誤検出が業務上の障害となった場合を含む．
- 上流 `textlint-rule-ja-no-mixed-period` にノード種別除外機能が
  追加されたとき．`ignoreNodeTypes` 相当のオプションを想定する．

## 参照

- [Issue #57](https://github.com/tomio2480/github-workflows/issues/57) —
  本件の起票・調査コメント
- [Issue #15](https://github.com/tomio2480/github-workflows/issues/15) —
  同種の「経緯保管」運用の先例
- [techbook-introduction-to-electronics-basic-led#3](https://github.com/tomio2480/techbook-introduction-to-electronics-basic-led/issues/3) —
  発端となった校閲 Issue
- [docs/dictionary-maintenance.md](../dictionary-maintenance.md) —
  caller-side allowlist / override の運用指針
