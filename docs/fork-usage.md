# 🔀 フォーク運用の手引き

## 要約

`tomio2480/github-workflows` を自分のアカウントへフォークして運用するための手順．フォーク後に composite action 本体（`.github/actions/markdown-lint/action.yml`）を書き換える必要はない．`$GITHUB_ACTION_PATH` ベースの自己検出ロジックにより，どのオーナーから呼び出されても自動的に正しい設定が読み込まれる．利用者が触るのは caller workflow の `OWNER` プレースホルダー置換と SHA pin（または `v2` タグ）管理のみ．

> [!IMPORTANT]
> 本ドキュメント中の例で示している `tomio2480/github-workflows` はそのままコピペせず，フォーク利用時は **`OWNER` 部分を必ず自分の GitHub ユーザー名に置き換えてください** ．caller workflow（`templates/.github/workflows/md-lint.yml`）の `uses:` に出てくる `OWNER` プレースホルダーが置換対象です．

## 目次

- 🎯 フォーク運用に向いているケース
- 1️⃣ フォークを作成
- 2️⃣ v2 タグを打つ
- 3️⃣ 対象 repo の caller で自分のフォークを参照
- 4️⃣ 上流（tomio2480）との同期
- 5️⃣ 辞書・ルールの独自カスタム
- 📚 参考

## 🎯 フォーク運用に向いているケース

- 組織運用で全 repo に統一ルールを適用したい
- 独自の表記ゆれ辞書を育てたい
- 破壊的変更のタイミングを自分で制御したい
- 上流の lint ルールと合わない部分がある

個人で Tomio さんのルールに異存がない利用者は [パターン (A) の直接参照](onboarding-new-repo.md) のほうが保守コストが低い．

## 1️⃣ フォークを作成

```bash
gh repo fork tomio2480/github-workflows --clone=false
```

`--clone=false` でローカル clone をスキップしている．必要なら clone する．

UI から行う場合は GitHub の `https://github.com/tomio2480/github-workflows` で Fork ボタン．

## 2️⃣ v2 タグを打つ（任意）

caller テンプレートの既定は SHA pin + バージョンコメント（ `@<SHA> # v2` ）．フォーク直後でも commit SHA さえ控えれば即運用可能．タグは Dependabot の major version 追随や release notes 管理を簡単にしたい場合に opt-in で打つ．

```bash
# 安定点での milestone として（推奨）
gh release create v2 \
  --repo YOUR_USERNAME/github-workflows \
  --target main \
  --title "v2" \
  --notes "Forked from tomio2480/github-workflows v2 (composite action)"
```

`@main` 参照の caller は main 更新に自動で追随するため，タグを打たなくても最新ルールは届く．破壊的変更（inputs 互換性の変更など）をする場合は `@main` 利用者にも影響するので事前に周知し，pinning 利用者を増やしたいときのみ `v2` タグを用意する．さらに破壊的変更を重ねる場合は `v3` を新規に切って `v2` は旧状態で残す．

> [!WARNING]
> 上流の `v1` タグ（reusable workflow 形式）は self-detection bug により動作しません．フォークしても `v1` タグを引き継いだり打ち直したりしないでください．composite action 形式の v2 以降を採用してください．

## 3️⃣ 対象 repo の caller で自分のフォークを参照

```bash
cd /path/to/target-repo
mkdir -p .github/workflows

OWNER=YOUR_USERNAME

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/main/templates/.github/workflows/md-lint.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  > .github/workflows/md-lint.yml

cat .github/workflows/md-lint.yml
```

テンプレートの `uses:` 行は `OWNER/github-workflows/.github/actions/markdown-lint@<SHA> # v2` 形式で出力される．`OWNER` を `YOUR_USERNAME` に，`<SHA>` をフォーク先の commit SHA に置換すれば caller として完成．即時反映を優先したい repo だけ `@<SHA>` 部分を `@main` に書き換える．

## 4️⃣ 上流（tomio2480）との同期

上流の更新（composite action 改修・辞書追加など）を取り込むときの手順．

main への直接 push はしない．独自変更の有無にかかわらず **同期ブランチ + Draft PR** で取り込む．

```bash
gh repo clone YOUR_USERNAME/github-workflows
cd github-workflows

git remote add upstream https://github.com/tomio2480/github-workflows.git
git fetch upstream

# 同期ブランチで取り込み
git checkout -b sync/upstream-$(date +%Y%m%d)
git merge upstream/main
# コンフリクト解消があれば対応

# push・PR 作成はユーザー確認のうえ実施
# git push -u origin sync/upstream-$(date +%Y%m%d)
# gh pr create --draft --title "Sync upstream main" --body "..."
```

main にマージされると `@main` 参照の caller には次回 PR から新しい内容が反映される．SHA pin 利用者は Dependabot の更新 PR を経由して取り込むため自動的に追随する．

```bash
# patch リリース（PR マージごとに実施）
git tag v2.2.1 main
git push origin v2.2.1
git tag -f v2 v2.2.1
git push -f origin v2
gh release create v2.2.1 --title "v2.2.1" --notes "..."
```

`-f` と `--force` はオーナー操作．pinning 利用している caller の影響範囲を確認し，stakeholder（caller repo のオーナー）に事前通知したうえで実施する．patch immutable（`v2.2.0` 等）に固定したい caller は，新 patch への切り替えを明示的に行う必要がある．major mutable（`v2`）に追従する caller は patch リリースで自動的に最新化される．

## 5️⃣ 辞書・ルールの独自カスタム

フォーク先で `templates/prh.yml` 等を自由に編集すればよい．caller は変更なしで，`@main` 参照なら次回 PR から新辞書が効く．SHA pin 利用者には Dependabot の更新 PR で伝わる．

表 1: 主なカスタム箇所

| ファイル | 主な変更ポイント |
|---|---|
| `templates/prh.yml` | 組織固有の用語・プロダクト名の表記ゆれ |
| `templates/.textlintrc.json` | `sentence-length.max`，`preferInBody` など組織の文体方針 |
| `templates/.markdownlint-cli2.yaml` | 組織として許容したい記法 |
| `.github/actions/markdown-lint/action.yml` | reviewdog の reporter / filter mode のデフォルト変更や step 追加 |

破壊的変更（既存 caller で急に指摘が増える，inputs の互換性が変わるなど）を入れるときは新メジャータグ（`v3`）を切り，caller 側で `@<新 SHA> # v3` へ切り替えてもらう運用にする．

## 📚 参考

- [docs/architecture.md](architecture.md)：自己検出ロジックの詳細
- [docs/security.md](security.md)：public 運用時の脅威モデル
- [docs/setup-guide.md](setup-guide.md)：中央リポジトリの新規立ち上げ
- [CLAUDE.md](../CLAUDE.md)：AI エージェント向けの作業規律
