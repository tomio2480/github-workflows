# 🤖 CLAUDE.md — github-workflows での作業指示

## 要約

このリポジトリで Claude Code / Claude Desktop 等の AI エージェントが作業するときの規律．通常の開発規律（`code-quality` / `github-dev` / `docs-quality` Skill）に加え，中央リポジトリとして多数の caller に影響を与える性質に由来するルールをまとめる．`reviewdog` による Bot 型 PR レビューを提供するため，公開運用時のセキュリティ配慮も必須．本リポジトリは composite action として配布する形式（v2 以降）．v1 は self-detection bug により動作しません．

## 目次

- 📋 このリポジトリの性質
- 🚨 変更時の注意
- 🔒 セキュリティ関連の遵守事項
- ✅ コミット・PR ルール
- 🔀 フォーク利用と OWNER プレースホルダー
- 📚 関連ドキュメント

## 📋 このリポジトリの性質

- 複数リポジトリから `uses:` で呼び出される composite action を管理する（v2 以降）
- caller テンプレートの既定は SHA pin + バージョンコメント（ `@<SHA> # v2` ）．`.github/actions/markdown-lint/action.yml` や `templates/` の変更は SHA pin 利用者に対し Dependabot 経由で更新 PR が起票される．`@main` 直接参照は Dependabot の追随対象外
- v1 タグ（reusable workflow 形式）は self-detection bug により動作しない．残置はするがリリースノートで非推奨を明示している
- reviewdog で PR inline コメントを投稿するため，caller 側に `pull-requests: write` 権限と `github-token` input への明示的な渡しが必要
- 公開（public）運用される．外部からのフォーク PR は原則マージしない

## 🚨 変更時の注意

### composite action の変更

- **破壊的変更は原則タグ付けで管理する**（例：`v2` / `v3`）
- **呼び出し側が SHA pin（ `@<SHA> # v2` ）または `@main` で参照している前提** を忘れない．意図しない影響を与えない
- 権限は `contents: read` + `pull-requests: write` を基本とし，必要な場合のみ明示的に拡張する
- `$GITHUB_ACTION_PATH` ベースの自己検出ロジックを破壊しないこと（caller checkout に依存しない設計）
- inputs の互換性を変える場合は major version cut を伴う
- third-party action の参照は **full commit SHA でピン**．タグ参照（`@v1`）への書き換えは供給網リスクを上げるため行わない

### テンプレート・設定ファイルの変更

- `templates/prh.yml` などの中央デフォルト設定は，`@main` 直接参照の caller では即時反映される．SHA pin 利用者には Dependabot 更新 PR を経由して伝わる．破壊的追加（既存 caller で誤検出が増える恐れ）は注意
- **PR マージごとに `vX.Y.Z` patch タグを切る**（patch 番号運用）．caller は `@v2.2.0` のような固定 patch を pin できる．immutable patch は GitHub Release を伴う
- **major mutable タグ（`v2` 等）は最新 patch に追従させる**．PR マージ後に `git tag -f v2 <new-sha>` で進める．`@v2` pin 利用者は次回 PR で自動的に最新 patch を受け取る
- 設定構造そのものの変更（既存 inputs の意味変更や required 化）は次の major version 相当として扱う
- 変更は `docs/` の手順にも反映する．とくに [docs/architecture.md](docs/architecture.md) と [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md) の記述が古くならないこと

### ドキュメントの変更

- AI エージェント・人間の両方が参照することを意識する
- 章構成・見出し・表番号・図番号の規約を守る（ユーザーのグローバル規律を遵守）
- 参照リンクは相対パスで書く

## 🔒 セキュリティ関連の遵守事項

詳細は [docs/security.md](docs/security.md)．特に以下を守ること．

- `pull_request_target` を使うワークフローは追加しない
- `secrets: inherit` は使わない．必要な secret は個別に明示
- third-party action は full commit SHA で参照
- 外部からの PR を扱う場合は workflow・dependencies の変更を特に精査
- 共有タグの運用：major mutable（`v2`）は patch リリースごとに進める方針．後方非互換を伴う場合は新 major（`v3`）を切り旧 major は据え置く．`v1` は self-detection bug により動作しないため移動しない

## ✅ コミット・PR ルール

- `git push` は指示があるまで絶対に行わない
- Pull Request は **必ず Draft** で作成する
- ワークフローおよび composite action の変更は `act` 等でローカル検証，またはテスト用リポジトリから呼び出して動作確認する．本リポジトリには [.github/workflows/test-self-lint.yml](.github/workflows/test-self-lint.yml) で composite action の単体／統合テストが組まれている
- `scripts/` 配下に新規ロジックを追加する場合は `tests/` で test-first で書く．Red → Green → Refactor の順を守る
- コミットは論理単位で分ける（テスト追加／実装／テンプレ変更／ドキュメント更新 など）

## 🔀 フォーク利用と OWNER プレースホルダー

- composite action 本体は **オーナー名をハードコードしない**．`$GITHUB_ACTION_PATH` から自リポジトリのチェックアウト先絶対パスを取得し，そこから中央 templates へ相対参照する設計
- `templates/.github/workflows/md-lint.yml` には `OWNER/github-workflows` プレースホルダーを残す．`tomio2480` 直接利用者もフォーク利用者も同じテンプレを使える
- ドキュメントやコメントで例として `tomio2480` を使うのは OK．ただし「フォーク利用時はここを自分のユーザー名に」と必ず注意書きする

## 📚 関連ドキュメント

- [README.md](README.md) — リポジトリ概要・Quick Start
- [docs/setup-guide.md](docs/setup-guide.md) — 中央リポジトリ自体の立ち上げ
- [docs/onboarding-new-repo.md](docs/onboarding-new-repo.md) — 新規リポジトリ導入
- [docs/onboarding-existing-repo.md](docs/onboarding-existing-repo.md) — 既存リポジトリ導入
- [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md) — 辞書メンテナンス
- [docs/rule-rationale.md](docs/rule-rationale.md) — textlint / prh ルールの採用根拠
- [docs/architecture.md](docs/architecture.md) — 内部動作と自己検出ロジック
- [docs/security.md](docs/security.md) — 公開運用時の脅威モデル
- [docs/fork-usage.md](docs/fork-usage.md) — フォーク利用手順
- [docs/development-notes.md](docs/development-notes.md) — 設計判断とレビュー対応の知見（過去 PR のふりかえり）
