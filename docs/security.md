# 🔒 セキュリティガイド

## 要約

本リポジトリは public 運用される．中央リポジトリとして多数の caller に影響を与える性質上，供給網攻撃・承認なしフォーク PR 実行などのリスクを理解したうえで運用する．設計段階で `pull_request_target` や `secrets: inherit` を使わない方針を徹底し，third-party action は full commit SHA でピンする．オーナーが承認していない PR はマージしないことが最大の防御である．

## 目次

- 🎯 脅威モデル
- 🛡 設計による防御
- ⚙️ 必須の GitHub リポジトリ設定
- 🧪 運用ルール
- 📚 参考資料

## 🎯 脅威モデル

前提：

- オーナーは単独（共同メンテナーなし）
- 外部からの PR は原則マージしない
- 機密情報（API キー等）は本リポジトリに置かない

表 1: 攻撃シナリオと評価

| # | シナリオ | 評価 | 主な対策 |
|---|---|---|---|
| 1 | `pull_request_target` 悪用（pwn request） | 不成立 | 設計上不使用 |
| 2 | Fork からの PR で Actions が自動実行され，悪意ワークフローが走る | 低（初回承認必須） | 外部コラボ承認必須設定を有効化．リポジトリに `on: pull_request` のワークフローを追加する場合は必ず承認ポリシーを確認 |
| 3 | 悪意の PR を誤ってマージ | 人的リスク | 依存・ワークフロー変更は精査．typo 修正 PR でも workflow と dependencies の変更がないかを確認 |
| 4 | third-party action が侵害される | 実在 | full commit SHA でピン．Dependabot で更新追跡 |
| 5 | Secrets 漏洩 | 不成立 | `secrets: inherit` 不使用．caller から `inputs.github-token` で `GITHUB_TOKEN` を明示渡し |
| 6 | 共有タグ（`v2` など）の改竄 | 低（オーナーのみ書き込み可） | アカウントの 2FA と保護 |
| 7 | npm 供給網汚染（markdownlint-cli2 等） | 残存リスク | action 内部で管理．個別対策困難．受容 |
| 8 | 社会工学攻撃（typo 修正を装う） | 低〜中 | 外部 PR は原則マージしない |
| 9 | caller 側から見た破壊的変更 | 運用ミス | タグ運用（[CLAUDE.md](../CLAUDE.md)） |

「他人の要望や PR を取り込まなければ基本安全」は概ね正しい．追加で third-party action の SHA ピンと GitHub 設定強化を行えば公開運用に十分な安全性が得られる．

## 🛡 設計による防御

- `pull_request_target` 不使用
- `secrets: inherit` 不使用．composite action の場合 `secrets.*` は自動継承されないため `inputs.github-token` で明示的に受け取る．caller 側で `${{ secrets.GITHUB_TOKEN }}` を明示的に渡す責務
- third-party action は full commit SHA で参照
- `permissions:` は caller 側で必要最小限（`contents: read` + `pull-requests: write`）を明示．composite では caller の job 権限が直接効く
- Dependabot で週次アップデート PR．SHA ピンは Dependabot 対応

## ⚙️ 必須の GitHub リポジトリ設定

### Settings → Actions → General

表 2: Actions 設定

| 項目 | 設定値 |
|---|---|
| Actions permissions | Allow select actions を推奨．最低でも Allow all は避ける |
| Fork pull request workflows from outside collaborators | **Require approval for all outside collaborators** |
| Workflow permissions | **Read repository contents and packages permissions**（デフォルト read） |
| Allow GitHub Actions to create and approve pull requests | **OFF** |

### Settings → Branches

表 3: `main` のブランチ保護

| 項目 | 設定 |
|---|---|
| Require a pull request before merging | 有効 |
| Require approvals | 1 以上（個人 repo でもセルフレビュー推奨） |
| Dismiss stale pull request approvals when new commits are pushed | 有効 |
| Require status checks to pass before merging | 有効 |
| Do not allow bypassing the above settings | 有効 |
| Allow force pushes | 無効 |
| Allow deletions | 無効 |

### Settings → Security

- Dependabot alerts：**ON**
- Dependabot security updates：**ON**
- Secret scanning：**ON**（public repo は自動で有効）
- Code scanning：可能なら有効（CodeQL など）

### Settings → Collaborators and teams

- 自分以外に書き込み権限を付与しない（必要になったら都度追加）

## 🧪 運用ルール

- 外部からの PR は **原則マージしない**．typo 修正の名目でも `.github/workflows/` ・ `.github/actions/` ・ `dependabot.yml` が変わっていないか確認
- third-party action の SHA は Dependabot PR を通してのみ更新．手動書き換えは避ける
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
