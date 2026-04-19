# 🚀 新規リポジトリへの Markdown lint 導入手順

## 要約

新規作成したリポジトリに Markdown lint を導入する手順をまとめる．設定テンプレートのコピーと呼び出し側ワークフローの配置，そしてローカル hook の有効化までを含む．

## 目次

- 🔧 前提条件
- 1️⃣ 設定テンプレートのコピー
- 2️⃣ 呼び出し側ワークフローの配置
- 3️⃣ ローカル hook の有効化（任意）
- 4️⃣ 動作確認
- 5️⃣ コミットと PR

## 🔧 前提条件

- 対象リポジトリが既にクローン済み・カレントディレクトリがそのリポジトリルート
- 中央リポジトリ `tomio2480/github-workflows` が public で存在している
- Node.js がローカルにインストール済み（ローカル hook を使う場合）

## 1️⃣ 設定テンプレートのコピー

中央リポジトリの `templates/` 以下にあるファイルを，対象リポジトリのルートにコピーする．

```bash
# 対象リポジトリのルートにいる状態で
CENTRAL_REPO_TEMPLATES=~/workspace/github-workflows/templates

cp "${CENTRAL_REPO_TEMPLATES}/.markdownlint-cli2.yaml" .
cp "${CENTRAL_REPO_TEMPLATES}/.textlintrc.json" .
cp "${CENTRAL_REPO_TEMPLATES}/prh.yml" .
cp "${CENTRAL_REPO_TEMPLATES}/lefthook.yml" .
```

中央リポジトリをローカルに持っていない場合は， `curl` で直接取得してもよい．

```bash
BASE=https://raw.githubusercontent.com/tomio2480/github-workflows/main/templates
curl -sSL "${BASE}/.markdownlint-cli2.yaml" -o .markdownlint-cli2.yaml
curl -sSL "${BASE}/.textlintrc.json" -o .textlintrc.json
curl -sSL "${BASE}/prh.yml" -o prh.yml
curl -sSL "${BASE}/lefthook.yml" -o lefthook.yml
```

## 2️⃣ 呼び出し側ワークフローの配置

`.github/workflows/md-lint.yml` を配置する．テンプレート中の `OWNER` を `tomio2480` に置き換える．

```bash
mkdir -p .github/workflows

curl -sSL \
  https://raw.githubusercontent.com/tomio2480/github-workflows/main/templates/.github/workflows/md-lint.yml \
  | sed 's|OWNER/github-workflows|tomio2480/github-workflows|' \
  > .github/workflows/md-lint.yml
```

## 3️⃣ ローカル hook の有効化（任意）

既存の Node.js プロジェクトであれば `package.json` に lefthook を追加する．新規の非 Node.js プロジェクト（Python 等）で lefthook をローカルで使いたい場合は，独立した形で lefthook をインストールする．

### Node.js プロジェクトの場合

```bash
npm install -D lefthook \
  markdownlint-cli2 \
  textlint \
  textlint-rule-preset-ja-technical-writing \
  textlint-rule-preset-ja-spacing \
  textlint-rule-prh

npx lefthook install
```

### 非 Node.js プロジェクトの場合

lefthook はバイナリ配布もあるため，プロジェクト外で導入する．

```bash
# macOS
brew install lefthook

# プロジェクトディレクトリで hook をインストール
lefthook install
```

lint ツール自体は `npx -y` で on-demand 取得させるか， CI のみで走らせる運用でも問題ない．

## 4️⃣ 動作確認

サンプル Markdown を作成して lint を走らせる．

```bash
cat > sample.md <<'EOF'
# サンプル

これはサンプルのドキュメントです．
githubのテストも含めて動作確認する．
EOF

npx -y markdownlint-cli2 "sample.md"
npx -y textlint "sample.md"
```

textlint 側で「github → GitHub」の指摘が出れば辞書が効いている．

## 5️⃣ コミットと PR

Skill のルールに従い， `git push` は指示があるまで行わない． Pull Request は Draft で作成する．

```bash
git checkout -b feature/introduce-markdown-lint
git add .
git commit -m "Introduce markdown lint (markdownlint-cli2 + textlint)"

# 必要に応じて push（要許可）
# git push -u origin feature/introduce-markdown-lint
# gh pr create --draft --title "Introduce markdown lint" --body "..."
```
