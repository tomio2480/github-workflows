# Issue #109 最終弾：fixture 指摘の扱いを現状維持とする判断

## 要約

Issue #109（本リポジトリ自身の textlint 既存指摘の段階的解消）の最終弾の記録である．
第 1〜3 弾で fixture 以外の指摘は 0 件になった．
残る指摘は `tests/fixtures/markdown/` の故意の違反 19 件のみである．
検証の結果，`.textlintignore` への追加は統合テストを壊すため行わない．
summary 集計からの除外は実装済みであり，現状維持で Issue をクローズする．

## 目次

- 背景
- 検証
- 判断
- 代替案と棄却理由
- 併せて実施した補正
- 参照

## 背景

Issue #109 は，self-lint が検出する既存指摘 283 件の段階的解消を扱う．
第 1 弾（PR #112）で `docs/notes/` の 93 件を解消した．
第 2 弾（PR #113）で `docs/architecture.md` と `docs/development-notes.md` の
88 件を解消した．
第 3 弾（PR #115）で残りの `docs/*.md`・`README.md`・`CLAUDE.md` の
82 件を解消した．

当初 283 件の内訳は，上記 3 弾の 263 件・fixture の 19 件・
git 未追跡ファイルの 1 件である（Issue 本文の集計に記載）．
未追跡の 1 件は `.pytest_cache/README.md` というローカル生成物であり，
リポジトリ管理外のため解消対象に含めない．

残るは `tests/fixtures/markdown/` の 19 件である．
これらは lint の検出能力を検証するため，故意に違反を含めた fixture である．
修正すると fixture の役割が失われるため，扱いの方針決定だけが残っていた．

## 検証

CI と同一構成のローカル走査で残件を確認した．構成は次のとおりである．

- 依存導入：`.github/actions/markdown-lint/package-lock.json` の `npm ci` ．
- 設定生成：`scripts/generate-textlint-runtime.py` による runtime 設定．
  入力は `templates/.textlintrc.json`・`templates/prh.yml`・`.prh-extra.yml` ．
- 除外指定：`--ignore-path .textlintignore` ．

結果は次のとおりである．

- fixture 以外の指摘：0 件（第 1〜3 弾の完了を確認）．
- fixture の指摘：19 件．内訳は `with-issues.md` が 12 件，
  `fullwidth-symbol-spacing.md` が 7 件である．

あわせて，Issue 本文で要検証とされていた統合テストの前提を確認した．
`test-self-lint.yml` の `integration-action` job を確認した．
この job は `markdown-glob` に `tests/fixtures/markdown/**/*.md` を渡す．
つまり fixture が lint 対象に入ることを前提とした構成である．

## 判断

`.textlintignore` へ `tests/fixtures/` を追加せず，現状維持とする．
根拠は次の 3 点である．

1. root の `.textlintignore` は意図して空にしてある．
   composite action は caller-first で ignore 設定を解決する．
   ここへ fixture を足すと `integration-action` job の走査対象が消える．
   統合テストの目的が失われるため追加できない．
2. summary 件数の集計からは除外済みである．
   dogfooding 用 caller（`.github/workflows/md-lint.yml`）が
   `markdown-ignore` input へ `tests/fixtures/**` を渡している．
3. inline コメントは `filter-mode: added` により PR 差分行のみに付く．
   fixture へ指摘が付くのは fixture を編集した PR に限られ，
   これは検出能力の確認として意図した挙動である．

以上により，fixture の 19 件は「解消すべき負債」ではなく
「テストに必要な検出対象」と位置づけ，Issue #109 をクローズする．

## 代替案と棄却理由

- `.textlintignore` へ `tests/fixtures/` を追加する案：
  上記のとおり統合テストの走査対象が消えるため棄却した．
- fixture の違反を修正する案：
  lint の検出能力を検証する fixture の役割と矛盾するため棄却した．
- self-lint 専用の ignore 設定を別途持つ案：
  `markdown-ignore` input による集計除外で目的を達成済みであり，
  設定の二重管理を増やすだけのため棄却した．

## 併せて実施した補正

テンプレ版コメントのドリフトを補正した．
対象は `templates/` 配下の `md-lint.yml` と `claude-review.yml` である．
版コメントが `# v2.10.0` のまま残っていた（v2.10.1 リリース時の記載齟齬）．
版コメントは「このコミットが属するリリースの番号」を書く規律に従い，
本 PR のリリース番号 `# v2.10.6` へ更新した．

## 参照

- Issue #109（textlint 既存指摘の段階的解消）
- PR #112・#113・#115（第 1〜3 弾）
- [タグ運用ドリフトと版コメント齟齬から得た知見](2026-08-09-tag-drift-and-version-comment-lessons.md)
- [.textlintignore](../../.textlintignore)（root で fixture を除外しない意図のコメント）
- [test-self-lint.yml](../../.github/workflows/test-self-lint.yml)
