# 📚 github-workflows

## 要約

Markdown を書くすべてのリポジトリに，PR にコメントする Bot 型の lint レビューを最小設定で導入するための中央リポジトリである．対象リポジトリは **1 ファイル** の caller workflow を置くだけで運用に乗る．caller workflow は既定で `@main` を参照するため，中央の辞書・ルール更新は `@main` 利用者へ次回 PR から即反映される．破壊的変更を避けたい利用者は `@v1`（系列最新）や `@v1.0.0`（不変）に差し替えて固定できる．`tomio2480/github-workflows` を直接参照してもよいし，自分のアカウントへフォークして独立運用してもよい．

## 目次

- 🎯 このリポジトリでできること
- 🗂 ディレクトリ構成
- 🚀 人間向け Quick Start
- 🤖 AI エージェント向け Quick Start
- 🧩 仕組みの概略
- ⚙️ 設定の上書き（per-repo override）
- 🔀 フォーク運用の手引き
- 🔒 セキュリティ
- 📚 ドキュメント一覧
- 📝 ライセンス

## 🎯 このリポジトリでできること

導入した対象リポジトリで PR を作成すると，次のことが自動で起きる．

- Markdown 記法の問題を [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2) が検出
- 日本語文章の問題を [textlint](https://textlint.github.io/) が検出（長文，混在文末，助詞連続など）
- 表記ゆれを [prh](https://github.com/prh/prh) が検出（GitHub 表記など）
- これらの指摘が [reviewdog](https://github.com/reviewdog/reviewdog) 経由で **PR の該当行に inline コメント** として投稿される
- CI 自体は緑のまま（マージをブロックしない）

Gemini Code Assist や CodeRabbit の Bot 的な使い勝手を，無料で自前運用する構成である．

## 🗂 ディレクトリ構成

```
github-workflows/
├── .github/
│   ├── workflows/
│   │   └── markdown-lint.yml   # 再利用可能ワークフロー本体
│   └── dependabot.yml          # third-party action の自動更新
├── templates/                  # 各リポジトリにコピーするテンプレート
│   ├── .github/
│   │   └── workflows/
│   │       └── md-lint.yml     # 呼び出し側ワークフロー（唯一の必須ファイル）
│   ├── .markdownlint-cli2.yaml # 中央デフォルト＋override 用
│   ├── .textlintrc.json        # 中央デフォルト＋override 用
│   ├── prh.yml                 # 中央辞書＋override 用
│   └── lefthook.yml            # ローカル hook（任意）
├── docs/                       # 運用ガイド
│   ├── setup-guide.md
│   ├── onboarding-new-repo.md
│   ├── onboarding-existing-repo.md
│   ├── dictionary-maintenance.md
│   ├── architecture.md
│   ├── security.md
│   └── fork-usage.md
├── README.md
├── CLAUDE.md                   # AI エージェント向けの作業指針
└── LICENSE
```

## 🚀 人間向け Quick Start

導入のパターンは 2 つある．どちらでも配置するファイルは caller workflow 1 枚だけ．

表 1: 導入パターンの比較

| 観点 | (A) tomio2480 を直接参照 | (B) フォークして独立運用 |
|---|---|---|
| 追加作業 | 対象 repo に 1 ファイル配置 | フォーク＋1 ファイル配置（`v1` タグは opt-in） |
| ルール変更の自由度 | 自分の repo 内で override のみ | 中央設定そのものを編集可能 |
| アップデート（`@main`） | 中央 main へのマージで次回 PR から即反映 | 自分でフォーク先に上流同期すると反映 |
| アップデート（`@v1` / `@v1.0.0`） | 中央が `v1` タグを移動したときのみ反映 | 自分のフォーク側で `v1` を移動したときのみ反映 |
| おすすめ対象 | Tomio さん本人 / ルールに異存がない利用者 | 組織運用 / ルールを独自カスタムしたい利用者 |

参照先（`@` 以降）は caller workflow で選ぶ．既定の `@main` は最新を追随し，破壊的変更を避けたい場合は `@v1`（系列最新）・`@v1.0.0`（不変）に差し替えて固定する．

### パターン (A)：tomio2480/github-workflows を直接参照

対象リポジトリのルートで以下を実行する．

```bash
mkdir -p .github/workflows
curl -sSL \
  https://raw.githubusercontent.com/tomio2480/github-workflows/main/templates/.github/workflows/md-lint.yml \
  | sed 's|OWNER/github-workflows|tomio2480/github-workflows|' \
  > .github/workflows/md-lint.yml
```

あとは PR を作るだけ．初回 PR で Actions の実行に権限承認が要求される場合があるので，リポジトリの Settings → Actions から許可する．

### パターン (B)：自分のアカウントへフォーク

```bash
# 1. フォーク
gh repo fork tomio2480/github-workflows --clone=false

# 2. 対象リポジトリでは OWNER を自分の名前に置換して caller を配置
mkdir -p .github/workflows
curl -sSL \
  https://raw.githubusercontent.com/YOUR_USERNAME/github-workflows/main/templates/.github/workflows/md-lint.yml \
  | sed 's|OWNER/github-workflows|YOUR_USERNAME/github-workflows|' \
  > .github/workflows/md-lint.yml
```

以後は自分のフォークを主軸に辞書やルールを育てていく．caller が `@main` を参照していれば自動で反映される．pinning したい利用者向けに `v1` / `v1.0.0` タグを打つのは任意．詳細は [docs/fork-usage.md](docs/fork-usage.md) を参照．

### 導入後の挙動

1. PR を作成すると Actions が走る
2. Actions は本リポジトリを checkout して設定を読み，caller repo の Markdown を lint する
3. 問題が見つかった行に，reviewdog が **PR レビューコメント** として自動投稿する（`filter-mode: added` のため，PR で追加・変更された行のみ）
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
2. ユーザーに **導入パターン** を確認する（(A) 直接参照か (B) フォークか）．判定迷うなら個人用途は (A)，組織用途は (B) を推奨
3. 該当する onboarding ドキュメントの手順を実行
4. **push は指示があるまで行わない**．Pull Request は必ず Draft で作成する
5. 導入後の挙動をユーザーに説明する（初回 PR で reviewdog コメントが付くこと）

### 2. 辞書や lint ルールの追加を依頼された場合

1. 対象が中央の辞書か repo 個別の辞書かを確認
2. 中央辞書であれば [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md)
3. repo 個別であれば，対象 repo に `prh.yml` / `.markdownlint-cli2.yaml` / `.textlintrc.json` を置いて override

### 3. 自分が判断してよいことと，してはいけないこと

| 事項 | 判断主体 |
|---|---|
| ドキュメントの軽微な誤字修正 PR | AI で自動対応可 |
| 設定ルールの無効化・変更 | ユーザー確認必須 |
| 辞書（prh.yml）への追加 | AI が提案，ユーザー確認してマージ |
| `@v1` タグの移動 | ユーザーのみ |
| 外部からの PR マージ | ユーザーのみ |
| 中央 repo 自体の破壊的変更 | ユーザー確認必須かつ新バージョンタグが前提 |

## 🧩 仕組みの概略

表 2: 各レイヤーの責務

| レイヤー | 何をするか | いつ |
|---|---|---|
| 開発者 | `.md` を編集して push | 任意のタイミング |
| lefthook（任意・ローカル） | `git push` を手元で hook して lint．NG なら push ブロック | `git push` 直前 |
| GitHub Actions（caller） | PR に反応してジョブを起動（テンプレート既定は `pull_request` のみ） | PR 作成・更新時 |
| 再利用可能ワークフロー（中央） | caller と中央の設定から lint を実行，reviewdog で inline コメント | caller ジョブ内 |
| 中央リポジトリ | ルール・辞書・ワークフローの source of truth | 常に |

詳細な内部フローは [docs/architecture.md](docs/architecture.md) を参照．

## ⚙️ 設定の上書き（per-repo override）

対象リポジトリのルートに同名ファイルを置くと，そのファイルが中央設定より優先される．

表 3: override 対象ファイル

| 置くファイル | 効果 |
|---|---|
| `.markdownlint-cli2.yaml` | markdownlint のルールを全置換 |
| `.textlintrc.json` | textlint のルールを全置換 |
| `prh.yml` | 辞書を全置換（中央辞書は無視される） |

override は **ファイル全置換方式** であり，差分マージはしない．中央を基点にしたいときは中央の該当ファイルをコピーして，必要部分だけ改変する．

## 🔀 フォーク運用の手引き

フォーク後に **再利用可能ワークフロー本体（`.github/workflows/markdown-lint.yml`）は一切変更する必要がない**．これは `github.workflow_ref` を使った自己検出ロジックのおかげ．利用者は caller 側で `OWNER` を自分のユーザー名に置き換えるだけでよい．

表 4: フォーク利用時の作業

| 作業 | 頻度 |
|---|---|
| `tomio2480/github-workflows` を自分のアカウントにフォーク | 初回 1 回 |
| 自分のフォークに `v1` タグを打つ | 初回 1 回．以後メジャー変更時のみ |
| 各対象 repo に caller 配置（OWNER → 自分の名前） | repo ごと 1 回 |
| 上流の更新を取り込む | 任意（週次・月次など） |

詳細は [docs/fork-usage.md](docs/fork-usage.md) を参照．

## 🔒 セキュリティ

本リポジトリは **public** 運用される．公開運用時の脅威モデルと推奨設定は [docs/security.md](docs/security.md) に記載．要点のみ以下．

- `pull_request_target` は一切使用しない．`secrets: inherit` も使わない
- third-party action は full commit SHA でピン．Dependabot で更新追跡
- Settings → Actions → General で「外部コラボレーターの Actions 実行に承認必須」を有効化
- 外部からの PR は原則マージしない．依存変更は特に精査

## 📚 ドキュメント一覧

表 5: ドキュメント一覧

| ファイル | 用途 | 主な読者 |
|---|---|---|
| [docs/setup-guide.md](docs/setup-guide.md) | 中央リポジトリ自体のセットアップ・運用 | 中央 repo オーナー |
| [docs/onboarding-new-repo.md](docs/onboarding-new-repo.md) | 新規 repo 導入 | 利用者・AI |
| [docs/onboarding-existing-repo.md](docs/onboarding-existing-repo.md) | 既存 repo 導入 | 利用者・AI |
| [docs/dictionary-maintenance.md](docs/dictionary-maintenance.md) | 辞書運用 | 利用者・AI |
| [docs/architecture.md](docs/architecture.md) | 内部動作 | メンテナー・AI |
| [docs/security.md](docs/security.md) | 公開運用の脅威モデル | オーナー |
| [docs/fork-usage.md](docs/fork-usage.md) | フォーク運用 | 他利用者 |

## 📝 ライセンス

MIT License（[LICENSE](LICENSE)）．再利用可能ワークフローという性格上，公開・再利用を許容するライセンスを選択している．
