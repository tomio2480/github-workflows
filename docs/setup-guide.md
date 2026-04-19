# 🏗 中央リポジトリのセットアップ手順

## 要約

`tomio2480/github-workflows`（またはフォーク）を新規に立ち上げるときのオーナー向け手順．すでに立ち上げ済みの既存中央リポジトリを運用する場合は [docs/architecture.md](architecture.md) と [docs/security.md](security.md) を参照．

## 目次

- 🔧 前提条件
- 1️⃣ 中央リポジトリを作成
- 2️⃣ 初期ファイルを配置
- 3️⃣ セキュリティ関連の GitHub 設定
- 4️⃣ v1 タグを打つ
- 5️⃣ 動作確認（ダミー caller で）

## 🔧 前提条件

- `gh` CLI が認証済み
- `git` が利用可能
- オーナー権限を持つ GitHub アカウント

## 1️⃣ 中央リポジトリを作成

```bash
gh repo create github-workflows \
  --public \
  --license mit \
  --description "Reusable GitHub Actions workflows and shared config templates"
```

public ライセンスを明示する．非公開運用したい場合は `--private`（ただし caller 側からの参照は同一アカウントか GitHub Enterprise 設定が必要）．

## 2️⃣ 初期ファイルを配置

本リポジトリをフォーク元として使う場合は `gh repo fork` が最速．新規に立てる場合は [パッケージ](https://github.com/tomio2480/markdown-lint-package) 相当の 13 ファイルを配置する．

配置対象：

- `.github/workflows/markdown-lint.yml`
- `.github/dependabot.yml`
- `templates/` 配下の 5 ファイル
- `docs/` 配下の 7 ファイル
- `README.md` / `LICENSE` / `CLAUDE.md`

## 3️⃣ セキュリティ関連の GitHub 設定

必ず [docs/security.md](security.md) を読んで以下を実施する．

- Settings → Actions → General → 「Require approval for all outside collaborators」
- Settings → Actions → General → Workflow permissions 「Read repository contents」
- Settings → Actions → General → Allow Actions to create PRs → **OFF**
- Settings → Branches → Branch protection on `main`
- Settings → Security → Dependabot alerts / security updates → **ON**

## 4️⃣ v1 タグを打つ

main ブランチが整ったら `v1` タグを打つ．caller は `@v1` で参照する．

```bash
gh release create v1 \
  --target main \
  --title "v1" \
  --notes "Initial stable release."
```

以降，破壊的でない変更は `v1` を動かさず main を更新してよい．ただし `@v1` が自動追随するので，明示的に動かす場合は `git tag -f v1 && git push -f origin v1`（オーナー操作・要注意）．

破壊的変更の場合は `v2` を新たに切る（[CLAUDE.md](../CLAUDE.md) 参照）．

## 5️⃣ 動作確認（ダミー caller で）

任意のテストリポジトリを用意し，[docs/onboarding-new-repo.md](onboarding-new-repo.md) に従って caller workflow を配置．PR を作って reviewdog コメントが付くことを確認する．

確認ポイント：

- `Checkout central configs` ステップで自分のリポジトリ名・ref が正しく検出されているか
- `Resolve config file paths` で期待どおりのパスが出力されているか
- reviewdog の markdownlint・textlint コメントが PR に投稿されているか
- CI ステータスが緑で終わっているか（`fail_on_error: false` のため）
