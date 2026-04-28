# 🔁 既存リポジトリへの Markdown lint 導入手順

## 要約

既存リポジトリに Bot 型 Markdown lint を後付け導入する手順．新規導入と違うのは **既存の Markdown ファイルが大量の指摘を出す可能性がある** 点だけ．reviewdog の `filter-mode: added` により PR で変更された行のみコメントされるため，既存ファイルが一斉にコメントで埋まる事態は起きない．ただし既存品質を底上げしたい場合の戦略も提示する．

## 目次

- 🔧 前提条件
- 1️⃣ 新規導入と同じ手順で導入
- 2️⃣ 既存指摘を棚卸し（任意）
- 3️⃣ 自動修正の一括適用（任意）
- 4️⃣ ルールを段階的に厳しくする戦略
- 5️⃣ コミットと PR

## 🔧 前提条件

- [docs/onboarding-new-repo.md](onboarding-new-repo.md) の手順を理解していること
- 対象リポジトリのデフォルトブランチが最新

## 1️⃣ 新規導入と同じ手順で導入

まずは [docs/onboarding-new-repo.md](onboarding-new-repo.md) の「1️⃣ caller workflow の配置」までをそのまま実施する．

この時点で新規 PR を作れば PR で変更された行のみ reviewdog コメントが付く．既存ファイルの指摘は PR に流れない．**ここまでで導入は完了**．以下は任意の品質底上げ作業．

## 2️⃣ 既存指摘を棚卸し（任意）

既存ファイル全体を lint して指摘を一覧化する．

**注意**：この時点で caller repo には中央設定ファイル（`.markdownlint-cli2.yaml` / `.textlintrc.json` / `prh.yml`）が無いため，`npx -y` コマンドは各ツールのデフォルト設定で動作する．中央設定の結果と一致させたい場合は，事前に中央テンプレートを取得してから lint を走らせる．また textlint は `.textlintrc.json` で指定されたプリセット・プラグインがローカルの `node_modules` に存在している必要があるため，事前に `npm install --no-save` で取得しておく．

```bash
# OWNER は tomio2480 または自分のユーザー名
OWNER=tomio2480

# 任意：Bot と同じ結果を見たい場合は中央設定を取得してから lint
curl -fsSL "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.markdownlint-cli2.yaml" -o .markdownlint-cli2.yaml
curl -fsSL "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.textlintrc.json" -o .textlintrc.json
curl -fsSL "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/prh.yml" -o prh.yml

# textlint のプリセット・プラグインをローカルに用意
npm install --no-save \
  textlint \
  textlint-rule-preset-ja-technical-writing \
  textlint-rule-preset-ja-spacing \
  textlint-rule-prh

# textlint には --ignore オプションが無い（--ignore-path のみ）．
# cwd の .textlintignore をデフォルトで読むため，node_modules 除外用のファイルを作成する．
# 既に .textlintignore がある場合はそれを尊重する．
[ -f .textlintignore ] || cat > .textlintignore <<'EOF'
node_modules/**
EOF

npx -y markdownlint-cli2 "**/*.md" "#node_modules" 2>&1 | tee markdownlint-report.txt
npx -y textlint "**/*.md" 2>&1 | tee textlint-report.txt
```

指摘を以下 3 分類でトリアージする．

表 1: トリアージ分類

| 分類 | 対応 |
|---|---|
| 手で直せるもの | 直す |
| ルール自体が不適切 | `.markdownlint-cli2.yaml` / `.textlintrc.json` でそのルールを無効化（override） |
| 個別のファイル・行だけ許容 | インラインコメントで例外指定 |

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

## 3️⃣ 自動修正の一括適用（任意）

自動修正可能な指摘をまず潰す．

**重要**：`--fix` はファイルを実際に書き換えるため，中央設定が手元に無い状態で実行するとツールのデフォルトルールで修正されてしまい，CI（Bot）と整合しない変更が大量に入る可能性がある．2️⃣ で中央 config を取得していない場合は事前に取得しておくこと．

```bash
# 2️⃣ で未取得なら先に取得（既に取得済みならスキップ）
OWNER=tomio2480
for f in .markdownlint-cli2.yaml .textlintrc.json prh.yml; do
  [ -f "$f" ] || curl -fsSL "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/$f" -o "$f"
done

# textlint のプリセット・プラグインがローカルに無ければ取得（2️⃣ で済んでいればスキップ）
[ -d node_modules/textlint-rule-preset-ja-technical-writing ] || npm install --no-save \
  textlint \
  textlint-rule-preset-ja-technical-writing \
  textlint-rule-preset-ja-spacing \
  textlint-rule-prh

# .textlintignore が無ければ作成（2️⃣ で作成済みならスキップ）．textlint には --ignore オプションが無いためファイル経由で除外する．
[ -f .textlintignore ] || cat > .textlintignore <<'EOF'
node_modules/**
EOF

npx -y markdownlint-cli2 --fix "**/*.md" "#node_modules" || true
npx -y textlint --fix "**/*.md" || true

git diff --stat
```

`|| true` を付けているのは，残指摘で終了コード非ゼロで落ちてもスクリプトを止めないため．

はてなブログ独自記法など自動修正で壊れる箇所はある．差分を目視確認し，意図しない書き換えは個別に revert する．

## 4️⃣ ルールを段階的に厳しくする戦略

既存ファイルが指摘だらけで一気に直せない場合は，**最初は緩いルールで通して，段階的に厳しくする** 戦略を取る．

override 用の `.textlintrc.json` を作り，しきい値を緩める．

```bash
# OWNER は tomio2480 または自分のユーザー名（onboarding-new-repo.md の設定と揃える）
OWNER=tomio2480

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.textlintrc.json" \
  > .textlintrc.json
```

`.textlintrc.json` で `sentence-length.max` を緩和：

```json
{
  "rules": {
    "preset-ja-technical-writing": {
      "sentence-length": { "max": 200 }
    }
  }
}
```

この状態で PR をマージし，以降の別 PR で上限を段階的に下げていく（200 → 150 → 100 → 80．最終的に中央既定の 80 まで戻す）．

## 5️⃣ コミットと PR

変更量が多いので **設定導入** と **既存ファイル修正** をコミット分離すると reviewer にやさしい．

```bash
git add .github/workflows/md-lint.yml
git commit -m "chore: introduce markdown lint caller workflow"

# 自動修正を入れた場合
git add "**/*.md"
git commit -m "style: apply markdown lint autofix to existing docs"

# override として実際に編集・採用するファイルだけを個別に git add する
# ※ 2️⃣ / 3️⃣ で curl したデフォルト設定や作成した .textlintignore は
#   「Bot と同じ結果をローカルで見る」ための一時ファイル．
#   override として採用しないものは意図せずコミットしないよう，削除するか .gitignore に追加する．
git add .textlintrc.json   # 実際に override として採用するファイルの例
git commit -m "chore: add per-repo markdown lint overrides"

# push・PR 作成はユーザー確認のうえ実施
```

Pull Request は **必ず Draft で作成する**．
