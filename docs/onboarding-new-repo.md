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
- 5️⃣ Claude レビュー workflow（任意）

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

# SHA pin 用に最新 v2 タグの commit SHA を取得する．
# 軽量タグなら .object.sha がそのまま commit を指す．
# annotated タグの場合は .object.type が "tag" になるため，さらに参照展開する．
SHA=$(gh api "repos/${OWNER}/github-workflows/git/refs/tags/v2" --jq '.object.sha')

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/md-lint.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/md-lint.yml

cat .github/workflows/md-lint.yml
```

出力を目視確認する．`uses:` 行の `OWNER` と `<SHA>` が実際の値に置換されていればよい．併記の版コメント（`# v2` 等）が実際の版と食い違う場合は手で合わせる．テンプレ取得元と SHA pin を同じリビジョン（`${SHA}`）に揃えているため，`main` が次版へ進んでいても新旧混在の caller は生成されない．

`gh release view v2 --json targetCommitish` は release が作成されたブランチ名（既定 `main`）を返すため commit SHA を保証しない．SHA 解決には上記 git refs API を使うこと．

## 2️⃣ 初回 PR で動作確認

```bash
git add .github/workflows/md-lint.yml
git commit -m "Introduce markdown lint via github-workflows composite action"
# push はユーザー確認後に実施
# git push -u origin feature/introduce-markdown-lint
# gh pr create --draft --title "Introduce markdown lint" --body "..."
```

Draft PR を作成すると Actions が起動し，変更された `.md` 行に問題があれば reviewdog が PR レビューコメントを付ける．初回は Actions の承認を求められる場合があるので GitHub UI で許可する．

## 3️⃣ ローカル hook（任意）

手元で `git push` を弾く pre-push hook が欲しい場合のみ．一人運用ならスキップしてよい．

ローカル hook で走る `markdownlint-cli2` と `textlint` が CI と同じ結果を出すためには，`lefthook.yml` だけでなく設定ファイル（`.markdownlint-cli2.yaml` / `.textlintrc.json` / `prh.yml`）もローカルに必要．導入時は 4 ファイルまとめて取得する．

### Node.js プロジェクト

```bash
npm install -D lefthook \
  markdownlint-cli2 \
  textlint \
  textlint-rule-preset-ja-technical-writing \
  textlint-rule-preset-ja-spacing \
  textlint-rule-prh

# 中央の設定ファイルと lefthook.yml を一括取得
# （1️⃣ で解決した ${SHA} を再利用し，caller が参照するリビジョンと揃える）
for f in .markdownlint-cli2.yaml .textlintrc.json prh.yml lefthook.yml; do
  curl -fsSL "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/$f" -o "$f"
done

npx -y lefthook install
```

### 非 Node.js プロジェクト

`lefthook` のバイナリを別途インストールし，以下のように `lefthook.yml` と 3 つの設定ファイルをまとめてコピーしてから `lefthook install` を実行する．

```bash
# 1️⃣ で解決した ${OWNER} / ${SHA} を再利用し，caller が参照するリビジョンと揃える
# （未設定の場合は 1️⃣ の解決手順を先に実行する）
for f in .markdownlint-cli2.yaml .textlintrc.json prh.yml lefthook.yml; do
  curl -fsSL "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/$f" -o "$f"
done

lefthook install
```

lint ツール自体は `npx -y` で on-demand 取得させるか，OS パッケージで別途用意する．

## 4️⃣ コミットと PR

基本の caller workflow は [2️⃣ 初回 PR で動作確認](#2%EF%B8%8F⃣-初回-pr-で動作確認) の時点で既にコミット済み．lefthook などを追加した場合のみ，以下を追加コミットする．

```bash
# 任意：ローカル hook を追加した場合だけ実行（未追加ならこの節をスキップ）
for f in lefthook.yml package.json package-lock.json; do
  [ -f "$f" ] && git add "$f"
done
git commit -m "chore: add local markdown lint hook"

# push・PR 作成はユーザー確認のうえ実施
```

Pull Request は **必ず Draft で作成する**．CLI では `gh pr create --draft` を使う．

## 5️⃣ Claude レビュー workflow（任意）

`@claude` メンションで起動するコードレビューを併せて導入できる．
配置するものは caller 1 枚と secret 1 件である．
前提条件と仕組みは [README の該当節](../README.md#-claude-レビュー-workflow任意) を参照．

```bash
# 1️⃣ で解決した ${OWNER} / ${SHA} を再利用する
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/claude-review.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/claude-review.yml
gh secret set CLAUDE_CODE_OAUTH_TOKEN  # 値は対話入力で渡す
```

`uses:` 行の SHA pin は sed で置換済みとなる．併記の版コメントだけ目視確認する．
workflow は default ブランチの定義で発火するため，追加した PR 自身では
メンションが発火しない．動作確認はマージ後の別 PR で行う．
