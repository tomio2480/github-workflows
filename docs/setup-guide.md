# 🏗 中央リポジトリのセットアップ手順

## 要約

`tomio2480/github-workflows`（またはフォーク）を新規に立ち上げるときのオーナー向け手順．すでに立ち上げ済みの既存中央リポジトリを運用する場合は [docs/architecture.md](architecture.md) と [docs/security.md](security.md) を参照．

## 目次

- 🔧 前提条件
- 1️⃣ 中央リポジトリを作成
- 2️⃣ 初期ファイルを配置
- 3️⃣ セキュリティ関連の GitHub 設定
- 4️⃣ ローカルテスト（pytest / bats）
- 5️⃣ v2 タグを打つ
- 6️⃣ 動作確認（ダミー caller で）

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

本リポジトリをフォーク元として使う場合は `gh repo fork` が最速．新規に立てる場合は [パッケージ](https://github.com/tomio2480/markdown-lint-package) 相当の一式（現行リポジトリ構成に合わせて配置する）を用意する．

配置対象：

- `.github/actions/markdown-lint/action.yml`（composite action 本体）
- `.github/workflows/test-self-lint.yml`（単体／統合テスト CI）
- `.github/dependabot.yml`
- `scripts/` 配下のスクリプト 2 本（`generate-textlint-runtime.py` / `resolve-config-path.sh`）
- `tests/` 配下（`python/` / `bash/` / `fixtures/markdown/`）
- `templates/` 配下の 5 ファイル
- `docs/` 配下の 7 ファイル
- `README.md` / `LICENSE` / `CLAUDE.md` / `.gitignore`

## 3️⃣ セキュリティ関連の GitHub 設定

必ず [docs/security.md](security.md) を読んで以下を実施する．

- Settings → Actions → General → 「Require approval for all outside collaborators」
- Settings → Actions → General → Workflow permissions 「Read repository contents」
- Settings → Actions → General → Allow Actions to create PRs → **OFF**
- Settings → Branches → Branch protection on `main`
- Settings → Security → Dependabot alerts / security updates → **ON**

## 4️⃣ ローカルテスト（pytest / bats）

`scripts/` 配下のロジックを変更したら，まずローカルで単体テストを通す．

```bash
# Python: pytest 5 ケース
python -m pip install -r tests/python/requirements.txt
python -m pytest tests/python -v

# Bash: bats 3 ケース．bats は npm 経由が手軽
npm install --no-save bats
npx bats tests/bash
```

GitHub Actions 上でも `.github/workflows/test-self-lint.yml` の `unit-python` / `unit-bash` job が同じ単体テストを，`integration-action` job が composite action の統合テストを走らせる．ローカルが緑でも CI が真の判定．

## 5️⃣ v2 タグを打つ（任意）

caller テンプレートの既定は SHA pin + バージョンコメント（ `@<SHA> # v2` ）．main に commit を積むと SHA pin 利用者には Dependabot 経由で更新 PR が起票される．`@main` 直接参照の利用者には次回 PR から即時反映される．

安定点（milestone）でタグを残したい場合は以下のように打つ．

```bash
gh release create v2 \
  --target main \
  --title "v2" \
  --notes "Initial stable release as composite action."
```

`@<SHA> # v2.x.y` 参照の利用者は SHA pin で固定されているので，タグを移動しても自動で SHA は変わらない．Dependabot の更新 PR を経由する．patch tag は PR マージごとに切る運用とし，major mutable（`v2`）も同時に最新 patch へ進める．caller は `@v2` で major mutable に追従するか，`@v2.2.0` のような patch immutable で固定するかを選べる．

> [!WARNING]
> `v1` タグは reusable workflow 形式で self-detection bug により動作しません．新規セットアップで `v1` を打ち直してはいけません．composite action 形式の v2 以降を採用してください．

## 6️⃣ 動作確認（ダミー caller で）

任意のテストリポジトリを用意し，[docs/onboarding-new-repo.md](onboarding-new-repo.md) に従って caller workflow を配置．PR を作って reviewdog コメントが付くことを確認する．

確認ポイント：

- `Resolve config file paths` ステップで `${GITHUB_ACTION_PATH}/../../../templates/` 配下のパスが解決されているか
- `Generate runtime textlint config with resolved prh path` で `${RUNNER_TEMP}/textlintrc.runtime.json` が生成されているか
- reviewdog の markdownlint・textlint コメントが PR に投稿されているか
- CI ステータスが緑で終わっているか（`fail_on_error: false` のため）
