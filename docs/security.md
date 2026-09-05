# 🔒 セキュリティガイド

## 要約

本リポジトリは public 運用される．中央リポジトリとして多数の caller に影響を与える性質上，供給網攻撃・承認なしフォーク PR 実行などのリスクを理解したうえで運用する．設計段階で `pull_request_target` や `secrets: inherit` を使わない方針を徹底する．third-party action は full commit SHA でピンする．オーナーが承認していない PR はマージしないことが最大の防御である．

## 目次

- 🎯 脅威モデル
- 🛡 設計による防御
- ⚙️ 必須の GitHub リポジトリ設定
- 🧪 運用ルール
- 📚 参考資料

## 🎯 脅威モデル

前提は次のとおり．

- オーナーは単独（共同メンテナーなし）
- 外部からの PR は原則マージしない
- 機密情報（API キー等）は本リポジトリに置かない

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）．以降の表も同様． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: 攻撃シナリオと評価

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| # | シナリオ | 評価 | 主な対策 |
|---|---|---|---|
| 1 | `pull_request_target` 悪用（pwn request） | 不成立 | 設計上不使用 |
| 2 | Fork からの PR で Actions が自動実行され，悪意ワークフローが走る | 低（初回承認必須） | 外部コラボ承認必須設定を有効化．リポジトリに `on: pull_request` のワークフローを追加する場合は必ず承認ポリシーを確認 |
| 3 | 悪意の PR を誤ってマージ | 人的リスク | 依存・ワークフロー変更は精査．typo 修正 PR でも workflow と dependencies の変更がないかを確認 |
| 4 | third-party action が侵害される | 実在 | full commit SHA でピン．Dependabot で更新追跡 |
| 5 | Secrets 漏洩 | 不成立 | `secrets: inherit` 不使用．caller から `inputs.github-token` で `GITHUB_TOKEN` を明示渡し |
| 6 | 共有タグ（`v2` など）の改竄 | 低（オーナーのみ書き込み可） | アカウントの 2FA と保護 |
| 7 | npm 供給網汚染（`markdownlint-cli2` 等） | 残存リスク | action 内部で管理．個別対策困難．受容 |
| 8 | 社会工学攻撃（typo 修正を装う） | 低〜中 | 外部 PR は原則マージしない |
| 9 | caller 側から見た破壊的変更 | 運用ミス | タグ運用（[CLAUDE.md](../CLAUDE.md)） |
| 10 | claude-review（`issue_comment` 発火）で cache 書き込み拒否警告 | 影響なし・受容 | `actions: write` 付与は見送り．最小権限を優先し警告を受容（Issue [#76](https://github.com/tomio2480/github-workflows/issues/76)） |
| 11 | `session-url-check` が検出行（PR 本文・コミットメッセージの一部）を `::error::` として echo し，公開 repo の Actions ログへ URL の複製が残る | 低 | セッション ID を `****` にマスクしてから出力する．出力はログ注釈のみで実行はしない．内容は投稿者自身が書いた PR の文字列である |
| 12 | 中央リポジトリ自身が comment 発火の workflow（`claude-review-self.yml`）を持ち，第三者のコメントで `pull-requests: write` を伴う job が起動しうる | 低 | `claude-code-action` が既定でコメント投稿者の write 権限を検査する．`allowed_non_write_users` は設定しない．checkout は ref 未指定（default ブランチのみ）で，PR head は取得しない．`contents` は read に絞る（Issue [#140](https://github.com/tomio2480/github-workflows/issues/140)） |

「他人の要望や PR を取り込まなければ基本安全」は概ね正しい．追加で third-party action の SHA ピンと GitHub 設定強化を行えば公開運用に十分な安全性が得られる．

## 🛡 設計による防御

- `pull_request_target` 不使用
- `secrets: inherit` 不使用．composite action の場合 `secrets.*` は自動継承されないため `inputs.github-token` で明示的に受け取る．caller 側で `${{ secrets.GITHUB_TOKEN }}` を明示的に渡す責務
- third-party action は full commit SHA で参照
- `permissions:` は caller 側で必要最小限（`contents: read` + `pull-requests: write`）を明示．composite では caller の job 権限が直接効く
- Dependabot で週次アップデート PR．SHA ピンは Dependabot 対応

## ⚙️ 必須の GitHub リポジトリ設定

### Settings → Actions → General

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2: Actions 設定

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 項目 | 設定値 |
|---|---|
| `Actions permissions` | Allow select actions を推奨．最低でも Allow all は避ける |
| `Fork pull request workflows from outside collaborators` | **Require approval for all outside collaborators** |
| `Workflow permissions` | **Read repository contents and packages permissions**（デフォルト read） |
| `Allow GitHub Actions to create and approve pull requests` | **OFF** |

### Settings → Branches

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 3: `main` のブランチ保護

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 項目 | 設定 |
|---|---|
| `Require a pull request before merging` | 有効 |
| `Require approvals` | 1 以上（個人 repo でもセルフレビュー推奨） |
| `Dismiss stale pull request approvals when new commits are pushed` | 有効 |
| `Require status checks to pass before merging` | 有効 |
| `Do not allow bypassing the above settings` | 有効 |
| `Allow force pushes` | 無効 |
| `Allow deletions` | 無効 |

### Settings → Security

- Dependabot alerts：**ON**
- Dependabot security updates：**ON**
- Secret scanning：**ON**（public repo は自動で有効）
- Code scanning：可能なら有効（CodeQL など）

### Settings → Collaborators and teams

- 自分以外に書き込み権限を付与しない（必要になったら都度追加）

## 🧪 運用ルール

- 外部からの PR は **原則マージしない**．typo 修正の名目でも `.github/workflows/`・`.github/actions/`・`dependabot.yml` が変わっていないか確認
- third-party action の SHA は Dependabot PR を通してのみ更新．手動書き換えは避ける
  - 走査対象は `.github/dependabot.yml` の `github-actions` に列挙した `/` と `/.github/actions/*` である．前者が `.github/workflows/` を，後者がネストした composite action を拾う（Issue #153）
  - **`templates/` だけは例外で手動更新とする．** caller 用の雛形であり，本リポジトリの workflow として実行されない．走査対象へ入れても Dependabot は扱わないためである．中央側と同じ SHA へ揃え，`tests/python/test_action_pins.py` でずれを検出する（Issue #156）
- `v2` などの共有タグを動かすときは以下を事前に行う：
  - 影響する caller repository の一覧化と影響範囲評価
  - 各 caller のオーナー（stakeholder）への事前通知と通知期間の確保
  - タグ移動時刻と `CHANGELOG` への明示的な記録
  - 問題時のロールバック手順（旧 commit SHA を控えておく）
- 破壊的変更は `v3`，`v4` として新タグを切り，旧タグは残す（v1 は self-detection bug により動作しないため復活させない）
- リポジトリの可視性を private に切り替えたい場合は caller の参照可能性に影響するため注意

## 📚 参考資料

- [GitHub Actions 公開リポジトリ防御ガイド (StepSecurity)](https://www.stepsecurity.io/blog/defend-your-github-actions-ci-cd-environment-in-public-repositories)
- [GitHub Actions 強化事例 (Wiz)](https://www.wiz.io/blog/github-actions-security-guide)
- [GitHub Actions セキュリティチートシート (GitGuardian)](https://blog.gitguardian.com/github-actions-security-cheat-sheet/)
- [Securing GitHub Actions Workflows (GitHub Well-Architected)](https://wellarchitected.github.com/library/application-security/recommendations/actions-security/)
- [Secure use reference (GitHub Docs)](https://docs.github.com/en/actions/reference/security/secure-use)
