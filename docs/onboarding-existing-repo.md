# 🔁 既存リポジトリへの Markdown lint 導入手順

## 要約

既存リポジトリに Markdown lint を後付け導入する手順をまとめる．既存の Markdown ファイルが大量の指摘を出す可能性が高いため，段階的な有効化と初期修正の戦略を含める．

## 目次

- 🔧 前提条件
- 1️⃣ 初期導入
- 2️⃣ 既存ファイルの一括修正
- 3️⃣ 残指摘のトリアージ
- 4️⃣ 段階的なルール有効化
- 5️⃣ コミットと PR

## 🔧 前提条件

- `docs/onboarding-new-repo.md` の手順（テンプレートコピーと caller workflow 配置）を先に実施済み
- 対象リポジトリのデフォルトブランチが最新状態

## 1️⃣ 初期導入

新規 repo と同じく，テンプレートをコピーして caller workflow を配置する．

```bash
# ブランチを切って作業開始
git checkout -b feature/introduce-markdown-lint

# （新規導入手順 2 までを実施）
```

## 2️⃣ 既存ファイルの一括修正

自動修正可能な指摘をまず潰す．

```bash
# markdownlint の自動修正
npx -y markdownlint-cli2 --fix "**/*.md" "#node_modules" || true

# textlint の自動修正
npx -y textlint --fix "**/*.md" || true
```

`|| true` を付けているのは，指摘が残っていても終了コード非ゼロで落とさないため．自動修正後に残る指摘だけを次の手順で扱う．

修正内容を差分で確認する．

```bash
git diff --stat
git diff
```

自動修正が意図しない書き換えをしている場合（はてなブログ独自記法の破壊など）は個別に revert する．

## 3️⃣ 残指摘のトリアージ

残った指摘を一覧化する．

```bash
npx -y markdownlint-cli2 "**/*.md" "#node_modules" 2>&1 | tee markdownlint-report.txt
npx -y textlint "**/*.md" 2>&1 | tee textlint-report.txt
```

指摘ごとに以下を判断する．

1. 手で直せるもの → 直す
2. ルール自体が不適切 → `.markdownlint-cli2.yaml` または `.textlintrc.json` でそのルールを無効化
3. 個別のファイル・行だけ許容したい → インラインコメントで例外指定

### インライン例外の書き方

markdownlint の場合：

```markdown
<!-- markdownlint-disable MD013 -->
長い行を含むテーブルなど
<!-- markdownlint-enable MD013 -->
```

textlint の場合：

```markdown
<!-- textlint-disable preset-ja-technical-writing/sentence-length -->
長めの文を許容したい箇所
<!-- textlint-enable -->
```

## 4️⃣ 段階的なルール有効化

既存ファイルの指摘が多すぎて一気に修正できない場合は， **最初は緩いルールで通るようにして，段階的に厳しくする** 戦略を取る．

例： `sentence-length` の上限を一時的に緩和する．

```json
{
  "rules": {
    "preset-ja-technical-writing": {
      "sentence-length": { "max": 200 }
    }
  }
}
```

導入 PR をマージしたあと，別 PR で上限を段階的に下げていく（200 → 150 → 100）．

## 5️⃣ コミットと PR

Skill のルールに従い， Pull Request は Draft で作成する．初期導入 PR は変更量が大きくなりがちなので， **設定追加のコミット** と **既存ファイルの自動修正コミット** を分けると reviewer にやさしい．

```bash
git add .markdownlint-cli2.yaml .textlintrc.json prh.yml lefthook.yml \
        .github/workflows/md-lint.yml package.json package-lock.json
git commit -m "chore: introduce markdown lint config and caller workflow"

git add "**/*.md"
git commit -m "style: apply markdown lint autofix to existing docs"

# push は指示があるまで行わない
# gh pr create --draft --title "Introduce markdown lint" --body "..."
```
