# 🏗 中央リポジトリのセットアップ手順

## 要約

`github-workflows` リポジトリを新規作成し，本パッケージの内容を初回コミットするまでの手順をまとめる．人手でも Claude Code でも実行できる形で記述する．

## 目次

- 🔧 前提条件
- 1️⃣ リモートリポジトリの作成
- 2️⃣ ローカルクローンと初期コミット
- 3️⃣ 動作確認
- 4️⃣ 次のステップ

## 🔧 前提条件

- GitHub アカウント（ `tomio2480` 等）にログイン済み
- `gh` CLI がインストール済み・認証済み（ `gh auth status` で確認）
- `git` が利用可能

## 1️⃣ リモートリポジトリの作成

`gh` CLI でリポジトリを作成する．ライセンスは MIT を選択し，README は初回コミットで含めるため `--add-readme` は付けない．

```bash
gh repo create github-workflows \
  --public \
  --license mit \
  --description "Reusable GitHub Actions workflows and shared config templates"
```

プライベート運用にしたい場合は `--public` を `--private` に変更する．ただし再利用可能ワークフローを private repo から呼び出すには GitHub Actions の設定が必要になるため，基本的には public を推奨する．

## 2️⃣ ローカルクローンと初期コミット

```bash
# 作業ディレクトリへ移動
cd ~/your-workspace

# 作成したリポジトリをクローン
gh repo clone tomio2480/github-workflows
cd github-workflows

# 本パッケージの github-workflows-repo/ 以下をコピー
# （展開済みの markdown-lint-package/ が ~/Downloads/ にあると仮定）
cp -r ~/Downloads/markdown-lint-package/github-workflows-repo/. ./

# コピー結果を確認
git status
```

コピー対象に `LICENSE` が含まれているかを確認する． `gh repo create --license mit` で既にリモートに `LICENSE` が作成されている場合は，ローカルの `LICENSE` で上書きしないよう注意する（ `git pull` で取得してからマージするのが安全）．

## 3️⃣ 動作確認

最初のコミットを作成するが， **push は指示があるまで行わない** （ Skill のルール）．

```bash
git add .
git commit -m "Initial commit: add markdown-lint reusable workflow and templates"

# 差分を確認
git log --oneline -5
git show --stat HEAD
```

内容を確認したうえで，ユーザーから push 指示があれば：

```bash
git push origin main
```

## 4️⃣ 次のステップ

- 最初の 1 リポジトリでの試験運用： `docs/onboarding-new-repo.md` または `docs/onboarding-existing-repo.md` を参照
- Claude Skills への規律反映： `docs-quality` Skill を参照
- 辞書の育成： `docs/dictionary-maintenance.md` を参照
