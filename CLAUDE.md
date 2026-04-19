# 🤖 CLAUDE.md — github-workflows での作業指示

## 要約

このリポジトリで Claude Code / Claude Desktop 等が作業するときのガイドライン．通常の開発規律（ `code-quality` / `github-dev` Skill）に加えて，このリポジトリ特有のルールをまとめる．

## 📋 このリポジトリの性質

- 複数リポジトリから呼び出される再利用可能ワークフローを管理する
- `.github/workflows/*.yml` への変更は，呼び出し側すべてに影響する
- `templates/` の変更は，新規導入時にコピーされるテンプレートを変える（既存コピーには自動反映されない）

## 🚨 変更時の注意

### 再利用可能ワークフローの変更

-  **破壊的変更は原則タグ付けで管理する** （例： `v1` / `v2` ）
-  **呼び出し側が `@main` で参照している前提を忘れない** ．意図しない影響を与えない
- 権限は `contents: read` を基本とし，必要な場合のみ明示的に拡張する

### テンプレートの変更

- 既存の呼び出し側に自動反映されない点に注意する
- 重要な変更は `docs/` の手順にも反映し，「既存リポジトリへのマイグレーション手順」として書く

## ✅ コミット・PR ルール

- `git push` は指示があるまで絶対に行わない
- Pull Request は必ず Draft で作成する
- ワークフローの変更は `act` 等でローカル検証，またはテスト用リポジトリから呼び出して動作確認する

## 📚 関連ドキュメント

- `README.md` — リポジトリ概要
- `docs/setup-guide.md` — 初回セットアップ
- `docs/onboarding-new-repo.md` — 新規リポジトリ導入
- `docs/onboarding-existing-repo.md` — 既存リポジトリ導入
- `docs/dictionary-maintenance.md` — 辞書メンテナンス
