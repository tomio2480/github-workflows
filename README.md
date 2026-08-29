# 📚 `github-workflows`

## 要約

Markdown lint と Shell / CLI quality の共通 GitHub Actions を配布する．
Markdown lint は v2 以降 composite action として配布する．
対象 repo は caller workflow 1 枚で導入できる．
Shell quality は任意の reusable workflow である．
caller repo の検証ロジックを中央の tool setup から実行する．
caller workflow は SHA pin + バージョンコメントを既定とする．
Dependabot は pin の更新を追随する．
中央 repo は直接参照しても，自分のアカウントへ fork してもよい．
v2.6 以降は，`@claude` で起動するレビュー用 workflow も配布する．

> [!IMPORTANT]
> **v1 タグ（reusable workflow 形式）は self-detection bug により動作しません．** v2 以降の composite action 形式へ移行してください．詳細は [Issue #3](https://github.com/tomio2480/github-workflows/issues/3) およびリリースノートを参照．

## 目次

- 🎯 このリポジトリでできること
- 🐚 Shell quality workflow（任意）
- 🤖 Claude レビュー workflow（任意）
- 🗂 ディレクトリ構成
- 🚀 人間向け Quick Start
- 🤖 AI エージェント向け Quick Start
- 🧩 仕組みの概略
- ⚙️ 設定の上書き（per-repo override）
- 🔀 フォーク運用の手引き
- 📐 採用ルールの根拠
- 🔒 セキュリティ
- 📚 ドキュメント一覧
- 📝 ライセンス

## 🎯 このリポジトリでできること

導入した対象リポジトリで PR を作成すると，次のことが自動で起きる．

- Markdown 記法の問題を [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2) が検出
- 日本語文章の問題を [textlint](https://textlint.github.io/) が検出（長文，混在文末，助詞連続など）
- 表記ゆれを [prh](https://github.com/prh/prh) が検出（GitHub 表記など）
- これらの指摘が [reviewdog](https://github.com/reviewdog/reviewdog) 経由で **PR の該当行に inline コメント** として投稿される
- 件数の summary コメントが PR に **1 件 upsert** される（指摘ゼロでも明示．push のたびに最新化）
- CI 自体は緑のまま（マージをブロックしない）

Gemini Code Assist や CodeRabbit の Bot 的な使い勝手を，無料で自前運用する構成である．

## 🐚 Shell quality workflow（任意）

`.github/workflows/shell-quality.yml` は，各 repo の local gate を実行する．
既定の command は `bin/verify-shell.py --require-all` である．
検証規則を中央へ移さず，tool の setup と local gate 呼び出しだけを再利用する．
ShellCheck，shfmt，Bats，PSScriptAnalyzer，Pester を共通 setup する．
local gate が非 0 を返すと job も失敗するブロッキング gate である．
Markdown lint の非ブロッキング動作とは異なる．

導入時は caller template を caller repo へコピーする．
対象は `templates/.github/workflows/shell-quality.yml` である．
`OWNER` は中央 repo の owner に置換する．
`<SHA>` は確定 commit SHA に置換する．
詳しい caller contract と固定 version は
[Shell / CLI quality reusable workflow](docs/shell-quality.md) を参照する．

## 🤖 Claude レビュー workflow（任意）

Markdown lint とは独立した任意機能である．caller を置いたリポジトリの
PR コメントで `@claude` をメンションすると発火する．
レビュー本体は
[claude-code-action](https://github.com/anthropics/claude-code-action)
が実行する．導入は「caller 1 枚 + secret 1 件」で完了する．

```bash
OWNER=tomio2480
mkdir -p .github/workflows

# SHA pin 用に最新 v2 タグの commit SHA を取得する
# （annotated タグの注意点は docs/onboarding-new-repo.md を参照）
SHA=$(gh api "repos/${OWNER}/github-workflows/git/refs/tags/v2" --jq '.object.sha')

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/claude-review.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/claude-review.yml
gh secret set CLAUDE_CODE_OAUTH_TOKEN  # 値は対話入力で渡す
```

生成後に caller を目視確認し，併記の版コメントが実際の版と
食い違う場合は手で合わせる．

前提は次の 2 点である．

- [Claude GitHub App](https://github.com/apps/claude) をインストール済みであること．
- Claude Pro / Max 契約で `claude setup-token` のトークンを発行できること．

メンション判定・権限・action の SHA pin は reusable workflow 側へ集約している．
中央の SHA 更新は，Dependabot 経由により SHA pin の caller へ波及する．
本 workflow は中央ファイルを自己参照しないため，
v1 md-lint の self-detection bug は該当しない．

### 既知の警告：cache 書き込み拒否

実行ログに `cache write denied: token has no writable scopes` という警告が
出る場合もある．本 workflow は `issue_comment` で発火する．
このため GitHub の Read-only Actions cache（低信頼トリガー向け）の対象になる．
その結果，`claude-code-action` 内部で cache 書き込みが拒否され，警告が生じる．
拒否されるのは `oven-sh/setup-bun` による bun 実行ファイルの cache 書き込みである．
レビュー結果の投稿を含む動作への影響は確認されていない．
警告を解消するには job へ `actions: write` を付与する必要がある．
ただし comment-triggered workflow へこの広い権限を与えるのは避けたい．
最小権限の方針（[docs/security.md](docs/security.md)）に反するため見送っている．
詳細は Issue [#76](https://github.com/tomio2480/github-workflows/issues/76) を参照．

## 🗂 ディレクトリ構成

```text
github-workflows/
├── .github/
│   ├── actions/
│   │   └── markdown-lint/
│   │       └── action.yml      # composite action 本体（v2）
│   ├── workflows/
│   │   ├── claude-review.yml   # Claude レビュー用 reusable workflow（v2.6〜）
│   │   ├── shell-quality.yml   # Shell / CLI quality reusable workflow
│   │   └── test-self-lint.yml  # 単体／統合テスト用 CI workflow
│   └── dependabot.yml          # third-party action の自動更新
├── scripts/                       # composite action から呼ぶ抽出ロジック（test-first 対象）
│   ├── add-pr-reaction.sh         # 👀 reaction 付与（fail-open）
│   ├── count-lint-findings.py     # textlint XML / markdownlint テキストから件数集計
│   ├── generate-mdlint-runtime.py # outputFormatters を除去した runtime config 生成
│   ├── generate-textlint-runtime.py
│   ├── install-lint-deps.sh       # lint 依存を lockfile から tmpdir へ npm ci
│   ├── post-lint-summary.sh       # PR に summary コメントを upsert（hidden marker / fail-open）
│   └── resolve-config-path.sh
├── tests/                         # スクリプト単体テスト + 統合テスト fixture
│   ├── python/                    # pytest
│   ├── bash/                      # bats-core
│   └── fixtures/
│       ├── markdown/              # Markdown lint 統合テスト fixture
│       └── shell-quality/         # Shell quality toolchain probe
├── templates/                     # 各リポジトリにコピーするテンプレート
│   ├── .github/
│   │   └── workflows/
│   │       ├── claude-review.yml  # Claude レビュー用 caller（任意）
│   │       ├── md-lint.yml        # 呼び出し側ワークフロー（lint 導入の必須ファイル）
│   │       └── shell-quality.yml  # Shell quality caller（任意）
│   ├── .markdownlint-cli2.yaml    # 中央デフォルト＋override 用
│   ├── .textlintrc.json           # 中央デフォルト＋override 用
│   ├── .textlintignore            # 中央 ignore 設定＋override 用
│   ├── .textlint-allowlist.yml    # caller-side allowlist のサンプル（v2.1〜，optional）
│   ├── .prh-extra.yml             # caller-side 追加 prh 辞書のサンプル（v2.7〜，optional）
│   ├── prh.yml                    # 中央辞書＋override 用
│   └── lefthook.yml               # ローカル hook（任意）
├── docs/                          # 運用ガイド
│   ├── setup-guide.md
│   ├── onboarding-new-repo.md
│   ├── onboarding-existing-repo.md
│   ├── dictionary-maintenance.md
│   ├── rule-rationale.md
│   ├── architecture.md
│   ├── security.md
│   ├── fork-usage.md
│   ├── development-notes.md       # 設計判断とレビュー対応の知見
│   ├── shell-quality.md            # Shell quality workflow の caller contract
│   └── notes/                     # 日付つき設計判断・実装知見メモ
├── README.md
├── CLAUDE.md                   # AI エージェント向けの作業指針
└── LICENSE
```

## 🚀 人間向け Quick Start

導入のパターンは 2 つある．どちらでも配置するファイルは caller workflow 1 枚だけ．

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）．以降の表も同様． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: 導入パターンの比較

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 観点 | (A) tomio2480 を直接参照 | (B) フォークして独立運用 |
|---|---|---|
| 追加作業 | 対象 repo に 1 ファイル配置 | フォーク＋1 ファイル配置（`v2` タグや SHA は opt-in） |
| ルール変更の自由度 | 自分の repo 内で override のみ | 中央設定そのものを編集可能 |
| アップデート（SHA pin + Dependabot） | Dependabot が更新 PR を起票 | 自分のフォーク側に Dependabot を設定する |
| アップデート（`@main`） | 中央 main へのマージで次回 PR から即反映 | 自分でフォーク先に上流同期すると反映 |
| おすすめ対象 | Tomio さん本人 / ルールに異存がない利用者 | 組織運用 / ルールを独自カスタムしたい利用者 |

参照先（`@` 以降）は caller workflow で選ぶ．既定は `@<SHA> # v2.2.0` 形式の SHA pin で，Dependabot が SHA とバージョンを自動追随する．即時反映を優先したい場合は `@main` を pin する．caller 自身で明示的に追従したい場合は `@v2`（major mutable）か `@v2.2.0`（patch immutable）を選ぶ．`@v2` は patch リリースごとに進む．`@v1` / `@v1.0.0` 系は self-detection bug により動作しないため利用しない．

### パターン (A)：`tomio2480/github-workflows` を直接参照

対象リポジトリのルートで以下を実行する．`OWNER` を 1 箇所だけ設定すれば URL と caller ファイル内部の両方に反映される．

```bash
OWNER=tomio2480
mkdir -p .github/workflows

# SHA pin 用に最新 v2 タグの commit SHA を取得する
# （annotated タグの注意点は docs/onboarding-new-repo.md を参照）
SHA=$(gh api "repos/${OWNER}/github-workflows/git/refs/tags/v2" --jq '.object.sha')

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/md-lint.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/md-lint.yml
```

テンプレ取得元と SHA pin を同じリビジョン（`${SHA}`）に揃えている．
`main` が次版へ進んでいても，新テンプレと旧参照の混在は起きない．
生成後に `uses:` 行を目視確認し，併記の版コメントが実際の版と食い違う場合は手で合わせる．

あとは PR を作るだけ．初回 PR では Actions の実行に権限承認を要求される場合がある．その際はリポジトリの Settings → Actions から許可する．

### パターン (B)：自分のアカウントへフォーク

```bash
# 1. フォーク
gh repo fork tomio2480/github-workflows --clone=false

# 2. 対象リポジトリでは OWNER を自分の名前に置換して caller を配置
OWNER=YOUR_USERNAME  # 自分の GitHub ユーザー名に置き換える
mkdir -p .github/workflows

# フォーク先 main の先頭 commit SHA を取得して pin する（v2 タグは opt-in のため）
SHA=$(gh api "repos/${OWNER}/github-workflows/commits/main" --jq '.sha')

curl -fsSL \
  "https://raw.githubusercontent.com/${OWNER}/github-workflows/${SHA}/templates/.github/workflows/md-lint.yml" \
  | sed "s|OWNER/github-workflows|${OWNER}/github-workflows|" \
  | sed "s|@<SHA>|@${SHA}|" \
  > .github/workflows/md-lint.yml
```

以後は自分のフォークを主軸に辞書やルールを育てていく．生成された caller は SHA pin のため，フォークの更新へ追随するには Dependabot 設定か手動更新が要る．即時反映を優先したい場合は `@<SHA>` 部分を `@main` へ書き換える．pinning したい利用者向けに `vX.Y.Z` 形式の patch タグと `vX` の major mutable を打つのは任意．詳細は [docs/fork-usage.md](docs/fork-usage.md) を参照．

### 導入後の挙動

1. PR を作成すると Actions が走る
2. Actions は本リポジトリを checkout して設定を読み，caller repo の Markdown を lint する
3. 問題が見つかった行に，reviewdog が **PR レビューコメント** として自動投稿する．対象は PR で追加・変更された行のみ（`filter-mode: added`）
4. lint 指摘だけでは CI を失敗させない（マージをブロックしない）．checkout・設定解決・setup 等の実行エラーは通常どおり失敗する．指摘はあくまで提案

## 🤖 AI エージェント向け Quick Start

このリポジトリを利用する Claude Code 等の AI エージェントは，以下の手順を守ること．

### 0. 必ず最初に参照するもの

1. 本 README（概念把握）
2. [CLAUDE.md](CLAUDE.md)（作業規律）
3. 対象の操作に応じた `docs/` 配下の該当ガイド

### 1. 対象リポジトリへの導入を依頼された場合

以下を順に実施する．途中でユーザー確認が必要な箇所は明示している．

1. 対象リポジトリのサイズと既存 Markdown の量を確認（`git ls-files '*.md' | wc -l`）
   - 新規または少数 → [docs/onboarding-new-repo.md](docs/onboarding-new-repo.md)
   - 多数 → [docs/onboarding-existing-repo.md](docs/onboarding-existing-repo.md)
2. ユーザーに **導入パターン** を確認する（(A) 直接参照 / (B) フォーク）．判定に迷うときの推奨は，個人用途 → (A)，組織用途 → (B)
3. 該当する onboarding ドキュメントの手順を実行
4. **push は指示があるまで行わない**．Pull Request は必ず Draft で作成する
5. 導入後の挙動をユーザーに説明する（初回 PR で reviewdog コメントが付くこと）

### 2. 辞書や lint ルールの追加を依頼された場合

1. 対象が中央の辞書か repo 個別の辞書かを確認
2. 中央辞書であれば [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md)
3. repo 個別であれば override を使う．対象 repo に `prh.yml` / `.markdownlint-cli2.yaml` / `.textlintrc.json` を置く

### 3. 自分が判断してよいことと，してはいけないこと

| 事項 | 判断主体 |
|---|---|
| ドキュメントの軽微な誤字修正 PR | AI で自動対応可 |
| 設定ルールの無効化・変更 | ユーザー確認必須 |
| 辞書（prh.yml）への追加 | AI が提案，ユーザー確認してマージ |
| major mutable タグ（`v2` 等）の移動 | ユーザーのみ |
| patch タグ（`v2.2.0` 等）の新規発行 | ユーザー確認のうえ AI が提案 |
| 外部からの PR マージ | ユーザーのみ |
| 中央 repo 自体の破壊的変更 | ユーザー確認必須かつ新バージョンタグが前提 |

## 🧩 仕組みの概略

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2: 各レイヤーの責務

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| レイヤー | 何をするか | いつ |
|---|---|---|
| 開発者 | `.md` を編集して push | 任意のタイミング |
| lefthook（任意・ローカル） | `git push` を手元で hook して lint．NG なら push ブロック | `git push` 直前 |
| GitHub Actions（caller） | PR に反応してジョブを起動し composite action を呼び出す（テンプレート既定は `pull_request` のみ） | PR 作成・更新時 |
| composite action（中央） | caller と中央の設定から lint を実行，reviewdog で inline コメント | caller ジョブ内 |
| 中央リポジトリ | ルール・辞書・action の source of truth | 常に |

詳細な内部フローは [docs/architecture.md](docs/architecture.md) を参照．

## ⚙️ 設定の上書き（per-repo override）

対象リポジトリのルートに同名ファイルを置くと，そのファイルが中央設定より優先される．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 3: override 対象ファイル

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 置くファイル | 効果 |
|---|---|
| `.markdownlint-cli2.yaml` | `markdownlint` のルールを全置換．`outputFormatters` は既定出力を壊すため除去される |
| `.textlintrc.json` | textlint のルールを全置換 |
| `prh.yml` | 辞書を全置換（中央辞書は無視される） |
| `.textlint-allowlist.yml` | caller 固有の例外語・例外パターン・例外ルールを差分追加（v2.1〜） |
| `.prh-extra.yml` | caller 固有の表記ゆれ規則を中央辞書に差分追加（v2.7〜） |

上 3 行の override は **ファイル全置換方式** であり，差分マージはしない．中央を基点にしたいときは中央の該当ファイルをコピーして，必要部分だけ改変する．

`.textlint-allowlist.yml` と `.prh-extra.yml` は差分追加方式で，中央の更新に追随したまま caller 単独の調整ができる．前者は固有名詞や法令名等の false positive を指摘から外し，後者は caller だけの表記ゆれ規則（読点の流儀など）を足す．同じ語を中央辞書と `.prh-extra.yml` の両方に書いた場合は中央が勝つ．中央規則を変えたいときは `prh.yml` の全置換を使う．使い分けは [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md) を参照．サンプルは [templates/.textlint-allowlist.yml](templates/.textlint-allowlist.yml) と [templates/.prh-extra.yml](templates/.prh-extra.yml) からコピーするとよい．

## 🔀 フォーク運用の手引き

フォーク後も **composite action 本体（`.github/actions/markdown-lint/action.yml`）は変更不要** である．`$GITHUB_ACTION_PATH` を起点にした相対参照で中央 templates を解決する設計のため，フォーク先からも本体を変えずに使える．利用者は caller 側で `OWNER` を自分のユーザー名に，`@<SHA>` を自分のフォークの commit SHA に置き換えるだけでよい．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 4: フォーク利用時の作業

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 作業 | 頻度 |
|---|---|
| `tomio2480/github-workflows` を自分のアカウントにフォーク | 初回 1 回 |
| 自分のフォークに `v2` タグや release を打つ | 初回 1 回．以後メジャー変更時のみ |
| 各対象 repo に caller 配置（OWNER → 自分の名前，SHA → 自分の commit） | repo ごと 1 回 |
| 上流の更新を取り込む | 任意（週次・月次など） |

詳細は [docs/fork-usage.md](docs/fork-usage.md) を参照．

## 📐 採用ルールの根拠

中央テンプレに同梱する textlint ルールセットは [JTF 日本語標準スタイルガイド](https://www.jtf.jp/pdf/jtf_style_guide.pdf) を基準に選定している．
業界慣習・組版・アクセシビリティ・データ整合性の 4 観点で評価し，少なくともひとつを満たすものを既定で有効化する．
caller 固有の例外は per-repo override で吸収する前提とし，中央側は「広く効く既定」を優先する．

問い合わせを受けやすい `ja-no-space-around-parentheses` の採用根拠や prh 辞書の表記指針は [docs/rule-rationale.md](docs/rule-rationale.md) にまとめている．

## 🔒 セキュリティ

本リポジトリは **public** 運用される．公開運用時の脅威モデルと推奨設定は [docs/security.md](docs/security.md) に記載．要点のみ以下．

- `pull_request_target` は一切使用しない．`secrets: inherit` も使わない
- third-party action は full commit SHA でピン．Dependabot で更新追跡
- Settings → Actions → General で「外部コラボレーターの Actions 実行に承認必須」を有効化
- 外部からの PR は原則マージしない．依存変更は特に精査

## 📚 ドキュメント一覧

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 5: ドキュメント一覧

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| ファイル | 用途 | 主な読者 |
|---|---|---|
| [docs/setup-guide.md](docs/setup-guide.md) | 中央リポジトリ自体のセットアップ・運用 | 中央 repo オーナー |
| [docs/onboarding-new-repo.md](docs/onboarding-new-repo.md) | 新規 repo 導入 | 利用者・AI |
| [docs/onboarding-existing-repo.md](docs/onboarding-existing-repo.md) | 既存 repo 導入 | 利用者・AI |
| [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md) | 辞書運用 | 利用者・AI |
| [docs/rule-rationale.md](docs/rule-rationale.md) | 採用ルールの根拠 | 利用者・AI |
| [docs/architecture.md](docs/architecture.md) | 内部動作 | メンテナー・AI |
| [docs/security.md](docs/security.md) | 公開運用の脅威モデル | オーナー |
| [docs/fork-usage.md](docs/fork-usage.md) | フォーク運用 | 他利用者 |
| [docs/development-notes.md](docs/development-notes.md) | 設計判断とレビュー対応の知見 | メンテナー・AI |
| [docs/shell-quality.md](docs/shell-quality.md) | Shell quality workflow の導入と契約 | 利用者・AI |

## 📝 ライセンス

MIT License（[LICENSE](LICENSE)）．composite action という性格上，公開・再利用を許容するライセンスを選択している．
