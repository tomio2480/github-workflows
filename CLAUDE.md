# 🤖 CLAUDE.md — github-workflows での作業指示

## 要約

このリポジトリで Claude Code / Claude Desktop 等の AI エージェントが作業するときの規律．通常の開発規律（`code-quality` / `github-dev` / `docs-quality` Skill）に加え，中央リポジトリとして多数の caller に影響を与える性質に由来するルールをまとめる．`reviewdog` による Bot 型 PR レビューを提供するため，公開運用時のセキュリティ配慮も必須．

## 目次

- 📋 このリポジトリの性質
- 🚨 変更時の注意
- 🔒 セキュリティ関連の遵守事項
- ✅ コミット・PR ルール
- 🔀 フォーク利用と OWNER プレースホルダー
- 📚 関連ドキュメント

## 📋 このリポジトリの性質

- 複数リポジトリから `workflow_call` で呼び出される再利用可能ワークフローを管理する
- `.github/workflows/*.yml` への変更は，`@v1`・`@main` 等で参照している **すべての caller に即波及** する
- `templates/` の変更は，新規導入時にコピーされるテンプレートを変えるが既存 caller にも **設定解決経由で** 反映される（中央デフォルトとしても使われるため）
- reviewdog で PR inline コメントを投稿するため，caller 側に `pull-requests: write` 権限が必要
- 公開（public）運用される．外部からのフォーク PR は原則マージしない

## 🚨 変更時の注意

### 再利用可能ワークフローの変更

- **破壊的変更は原則タグ付けで管理する**（例：`v1` / `v2`）
- **呼び出し側が `@v1` / `@main` で参照している前提** を忘れない．意図しない影響を与えない
- 権限は `contents: read` + `pull-requests: write` を基本とし，必要な場合のみ明示的に拡張する
- `github.workflow_ref` による自己検出ロジックを破壊しないこと（フォーク利用者の動作を壊す）
- third-party action の参照は **full commit SHA でピン**．タグ参照（`@v1`）への書き換えは供給網リスクを上げるため行わない

### テンプレート・設定ファイルの変更

- `templates/prh.yml` などは中央デフォルトとして即 caller に反映される．破壊的追加（既存 caller で誤検出が増える恐れ）は注意
- 設定構造そのものの変更は `v2` 相当として扱う
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
- `v1` などの共有タグを動かすときは事前に周知・影響範囲確認

## ✅ コミット・PR ルール

- `git push` は指示があるまで絶対に行わない
- Pull Request は **必ず Draft** で作成する
- ワークフローの変更は `act` 等でローカル検証，またはテスト用リポジトリから呼び出して動作確認する
- コミットは論理単位で分ける（ワークフロー変更／テンプレ変更／ドキュメント更新 など）

## 🔀 フォーク利用と OWNER プレースホルダー

- reusable workflow 本体は **オーナー名をハードコードしない**．`github.workflow_ref` から自己検出する設計
- `templates/.github/workflows/md-lint.yml` には `OWNER/github-workflows` プレースホルダーを残す．`tomio2480` 直接利用者もフォーク利用者も同じテンプレを使える
- ドキュメントやコメントで例として `tomio2480` を使うのは OK．ただし「フォーク利用時はここを自分のユーザー名に」と必ず注意書きする

## 📚 関連ドキュメント

- [README.md](README.md) — リポジトリ概要・Quick Start
- [docs/setup-guide.md](docs/setup-guide.md) — 中央リポジトリ自体の立ち上げ
- [docs/onboarding-new-repo.md](docs/onboarding-new-repo.md) — 新規リポジトリ導入
- [docs/onboarding-existing-repo.md](docs/onboarding-existing-repo.md) — 既存リポジトリ導入
- [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md) — 辞書メンテナンス
- [docs/architecture.md](docs/architecture.md) — 内部動作と自己検出ロジック
- [docs/security.md](docs/security.md) — 公開運用時の脅威モデル
- [docs/fork-usage.md](docs/fork-usage.md) — フォーク利用手順
