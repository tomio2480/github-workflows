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
- 6️⃣ Shell quality workflow（任意）
- 7️⃣ セッション URL 検査 workflow（任意）

## 🔧 前提条件

- 対象リポジトリが GitHub 上にあり，ローカルにクローン済み
- `gh` CLI が認証済み（`gh auth status` で確認）
- カレントディレクトリが対象リポジトリのルート

## 🔀 導入パターンの選択

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. 2 つの導入パターン

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

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

出力を目視確認する．`uses:` 行の `OWNER` と `<SHA>` が実際の値に置換されていればよい．併記の版コメントは major のみ（`# v2`）でよく，patch 番号へ書き換える必要はない．テンプレ取得元と SHA pin を同じリビジョン（`${SHA}`）に揃えているため，`main` が次版へ進んでいても新旧混在の caller は生成されない．

`gh release view v2 --json targetCommitish` は，release が作成されたブランチ名（既定 `main`）を返す．このため commit SHA を保証しない．SHA 解決には上記 git refs API を使うこと．

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

ローカル hook で走る `markdownlint-cli2` や `textlint` に，CI と同じ結果を出させたい．それには `lefthook.yml` だけでなく設定ファイルもローカルに必要である．対象は `.markdownlint-cli2.yaml` / `.textlintrc.json` / `prh.yml` の 3 つ．導入時は 4 ファイルまとめて取得する．

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

`lefthook` のバイナリを別途インストールする．以下のように `lefthook.yml` と 3 つの設定ファイルをまとめてコピーし，`lefthook install` を実行する．

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

基本の caller workflow は [2️⃣ 初回 PR で動作確認](#2️⃣-初回-pr-で動作確認) の時点で既にコミット済み．lefthook などを追加した場合のみ，以下を追加コミットする．

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

`uses:` 行の SHA pin は sed で置換済みとなる．併記の版コメントは major のみ（`# v2`）で固定である．

動作確認の経路は event ごとに違う．Issue #197 で実測した．

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2. コメント発火イベントの制約

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| event | 投稿する場所 | default ブランチ限定 | 追加した PR 自身で確認できるか |
|---|---|---|---|
| `issue_comment` | PR の会話タブ | 課される | できない |
| `pull_request_review_comment` | diff 行のレビューコメント | 課されない（観測） | 同一 repo の branch なら可 |

**同一リポジトリの branch なら，その PR 自身で動作確認できる．**
diff 行へ `@claude` を含むレビューコメントを投稿すればよい．
会話タブでの確認はマージ後の別 PR で行う．

限定が 2 つある．いずれも守れないと確認できない．

- **fork からの PR では使えない．** 発火するかどうか自体を確認していない．
  加えて fork 由来の run には repository secret が渡らず，
  `GITHUB_TOKEN` も read-only になるため Claude の応答まで到達しない．
- **公式ドキュメントの記述とは食い違う挙動である．** 2026-09-07 時点の観測であり，
  GitHub が文書どおりへ揃えれば使えなくなる．確認できなければ従来どおり
  マージ後の別 PR で行う．

経緯は [知見ノート](notes/2026-09-07-issue197-prc-trigger.md) を参照する．

## 6️⃣ Shell quality workflow（任意）

PowerShell または bash を持つリポジトリが対象である．
ShellCheck，shfmt，PSScriptAnalyzer，Bats-core，Pester を共通 setup する．
CLI ブラックボックステストを含む reusable workflow を導入できる．
詳細は [Shell / CLI 品質ゲート](shell-quality.md) を参照する．

対象リポジトリには，中央 workflow を呼ぶ caller と，リポジトリ固有の
`bin/verify-shell.py` を置く．`--require-all` は blocking gate とする．
必要なツールが欠けた場合や，検査が失敗した場合は非ゼロで終了する．
中央リポジトリに対象 repo 固有の検査ロジックは置かない．

```bash
# 1️⃣ で解決した ${OWNER} / ${SHA} を再利用する
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/shell-quality.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/shell-quality.yml

python bin/verify-shell.py --require-all
```

caller の `verify-script` と `paths` は，同じ検査スクリプトを指すように
更新する．導入 PR ではローカルの `--require-all` と GitHub Actions の
両方が成功することを確認する．

## 7️⃣ セッション URL 検査 workflow（任意）

Claude Code で commit や PR を作るリポジトリが対象である．
PR のタイトル・本文・コミットメッセージにセッション URL が残っていれば job を落とす．
caller の checkout は不要で，必要な権限は `contents: read` と `pull-requests: read` である．
詳細は [Claude セッション URL 検査 composite action](session-url-check.md) を参照する．

```bash
# 1️⃣ で解決した ${OWNER} / ${SHA} を再利用する
curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/session-url-check.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/session-url-check.yml
```

発生源を止める設定は Claude Code 側にある．`settings.json` へ
`attribution.sessionUrl: false` を置き，セッションを再起動する．
