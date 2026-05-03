# textlint v15 互換性検証と依存パッケージ更新

## 背景

`action.yml` の Install textlint step には以下のコメントが残置されていた．

> textlint は v14 系に固定する．textlint v15 は preset 側に ESM/exports field を要求するため，
> 現状 CommonJS の textlint-rule-preset-ja-technical-writing v12 系と組み合わせると
> rule が読み込まれず "No rules found" 状態になる．preset 側の対応を待つ間 v14 系で運用する．

Dependabot が textlint 14.8.4 → 15.6.0 の更新 PR（#40）を起票したため，
コメントの主張が現在も成立するか検証した．

## 判断

**v15 は CommonJS ルールと完全互換であることを確認し，v14 固定を解除した．**

### 検証手順

1. tmpdir を 2 つ用意し，v14.8.4 と v15.6.0 を独立インストール
2. 実際の使用パッケージ構成（`textlint-filter-rule-comments`・`textlint-rule-preset-ja-technical-writing` v12 等）をそのまま再現
3. `scripts/generate-textlint-runtime.py` で runtime config を生成
4. `tests/fixtures/markdown/with-issues.md` を両バージョンで実行して出力を比較

### 結果

| 確認項目 | v14.8.4 | v15.6.0 |
|---|---|---|
| ルール読み込み | 正常（8 件検出） | 正常（8 件検出） |
| 検出内容 | prh 3 件・ja-spacing 4 件・arabic-kanji-numbers 1 件 | **完全一致** |
| exit code | 1（issues found） | 1（issues found） |
| 出力差分 | — | サマリー末尾に `, 0 infos` が追加されただけ |

## 誤解の根拠推測

コメント当時の "No rules found" は v15 自体の制約ではなく，
`textlint-filter-rule-comments` が install されていなかったことによる既知の挙動だった可能性が高い．

action.yml 同ステップの直後のコメントに以下の記述があり，この不具合は以前から把握されていた．

> textlint-filter-rule-comments は中央 .textlintrc.json の filters.comments: true に対応する必須依存．
> これが install されていないと @textlint/config-loader の loadFilterRules で ReferenceError が発生し，
> TextlintrcLoader.js が ok:false を受けて空 rule で fallback する．

v15 の公式リリースノート・ブログ・Issue のいずれにも「CommonJS ルールを拒否する」仕様変更は確認されない．
v13 以降の `createLinter` は `import()` ベースのローダーを採用しており，CJS/ESM の両方を読み込める．

## Gemini SHA 誤検知のパターン

PR #43（setup-node v4.4.0 → v6.4.0 bump）の review で，
Gemini が SHA `48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e` を
「v4.2.0 相当」と誤指摘した（v4.2.0 の実 SHA は `1d0ff469b7ec7b3cb9d8673fde0c81c44821de2a`）．

GitHub API `repos/actions/setup-node/git/ref/tags/v6.4.0` で
`refs/tags/v6.4.0` と mutable `refs/tags/v6` の双方が当該 SHA を指すことを確認し，却下した．

Bot レビューが SHA とバージョンの対応を誤って指摘するケースがある．
指摘を受けた場合は GitHub API で一次確認してから採否を判断する．

## 代替案と棄却理由

- **上流（preset-ja-technical-writing）の ESM 対応を待つ**: 直近 6 か月はメンテが限定的で ESM 対応 Issue もなく，待機コストが高い．v15 が CJS を拒否しない以上，上流変更は不要．棄却．
- **v14 系の継続運用**: Node.js 24 がデフォルト LTS になった現在，v14 は Node.js 20 必須（v15 は 20+）なので差はない．v14 は 2025-06-22 で最終リリース済みで将来的なセキュリティ対応が期待できない．棄却．

## 参照

- Issue #42（setup-node Node.js 24 対応）: https://github.com/tomio2480/github-workflows/issues/42
- PR #40（textlint v15.6.0 bump）: https://github.com/tomio2480/github-workflows/pull/40
- PR #43（setup-node v6.4.0 bump）: https://github.com/tomio2480/github-workflows/pull/43
