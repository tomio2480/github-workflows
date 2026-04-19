# 🚀 新規リポジトリへの Markdown lint 導入手順

## 要約

対象リポジトリに置くファイルは **caller workflow 1 枚のみ**．`.markdownlint-cli2.yaml` 等の設定ファイルは中央リポジトリがデフォルトで提供するため不要．カスタムしたい場合だけ同名ファイルを置いて override する（[docs/architecture.md](architecture.md) 参照）．

## 目次

- 🔧 前提条件
- 🔀 導入パターンの選択
- 1️⃣ caller workflow の配置
- 2️⃣ 初回 PR で動作確認
- 3️⃣ ローカル hook（任意）
- 4️⃣ コミットと PR

## 🔧 前提条件

- 対象リポジトリが GitHub 上にあり，ローカルにクローン済み
- `gh` CLI が認証済み（`gh auth status` で確認）
- カレントディレクトリが対象リポジトリのルート

## 🔀 導入パターンの選択

表 1: 2 つの導入パターン

| パターン | 説明 | 向いているケース |
|---|---|---|
| (A) | `tomio2480/github-workflows` を直接参照 | 個人利用，Tomio さんのルールに異存がない |
| (B) | 自分のアカウントへフォークして参照 | 組織運用，独自ルールを育てたい |

以降 `OWNER` を (A) なら `tomio2480` に，(B) なら自分のユーザー名に読み替える．

## 1️⃣ caller workflow の配置

```bash
git checkout -b feature/introduce-markdown-lint

mkdir -p .github/workflows

# OWNER は tomio2480 または自分のユーザー名
OWNER=tomio2480

curl -sSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.github/workflows/md-lint.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  > .github/workflows/md-lint.yml

cat .github/workflows/md-lint.yml
```

出力を目視確認する．`uses: OWNER/github-workflows/...` が `uses: tomio2480/github-workflows/...` などに置換されていればよい．

## 2️⃣ 初回 PR で動作確認

```bash
git add .github/workflows/md-lint.yml
git commit -m "Introduce markdown lint via github-workflows reusable workflow"
# push はユーザー確認後に実施
# git push -u origin feature/introduce-markdown-lint
# gh pr create --draft --title "Introduce markdown lint" --body "..."
```

Draft PR を作成すると Actions が起動し，変更された `.md` 行に問題があれば reviewdog が PR レビューコメントを付ける．初回は Actions の承認を求められる場合があるので GitHub UI で許可する．

## 3️⃣ ローカル hook（任意）

手元で `git push` を弾く pre-push hook が欲しい場合のみ．一人運用ならスキップしてよい．

### Node.js プロジェクト

```bash
npm install -D lefthook \
  markdownlint-cli2 \
  textlint \
  textlint-rule-preset-ja-technical-writing \
  textlint-rule-preset-ja-spacing \
  textlint-rule-prh

# 中央の lefthook.yml をコピー
curl -sSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/lefthook.yml" \
  > lefthook.yml

npx lefthook install
```

### 非 Node.js プロジェクト

`lefthook` のバイナリを別途インストールし，`lefthook.yml` だけコピーしてプロジェクトの pre-push に登録する．

## 4️⃣ コミットと PR

```bash
git add .github/workflows/md-lint.yml
# 任意で追加したもの
git add lefthook.yml package.json package-lock.json

git commit -m "chore: introduce markdown lint (reusable workflow caller)"

# push・PR 作成はユーザー確認のうえ実施
```

Pull Request は **必ず Draft で作成する**．CLI では `gh pr create --draft` を使う．
