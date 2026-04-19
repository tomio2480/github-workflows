# 🧩 アーキテクチャ

## 要約

本リポジトリの再利用可能ワークフローが，caller リポジトリ・中央リポジトリ・reviewdog とどのように連携して PR に inline コメントを付けているかを説明する．自己検出による OWNER 非依存，設定ファイルの解決順序，および override のしくみを明らかにする．

## 目次

- 🗺 全体の流れ
- 🔍 自己検出のしくみ（`github.workflow_ref`）
- 📁 設定ファイルの解決順序
- 🐶 reviewdog の挙動
- 🔀 caller → reusable → reviewdog のデータフロー
- 🧪 トラブルシューティング

## 🗺 全体の流れ

図 1: PR 作成から PR コメントまでの流れ（データ flow）

```
開発者
  │ git push + Pull Request 作成
  ▼
対象リポジトリ（caller）
  │ .github/workflows/md-lint.yml が on: pull_request で起動
  │ uses: OWNER/github-workflows/.github/workflows/markdown-lint.yml@v1
  ▼
再利用可能ワークフロー（本リポジトリ）
  │ 1. caller repo を checkout
  │ 2. github.workflow_ref を解析して SELF_REPO / SELF_REF を抽出
  │ 3. SELF_REPO を .central-workflows/ へ checkout
  │ 4. caller に config があれば優先，なければ中央の templates/ を使う
  │ 5. textlint 用 runtime config を生成（prh のパスを解決）
  │ 6. Node.js setup
  │ 7. reviewdog/action-markdownlint → PR レビューコメント
  │ 8. tsuyoshicho/action-textlint → PR レビューコメント
  ▼
PR の該当行に inline コメントが付く
CI ステータスは常に緑（fail_on_error: false）
```

## 🔍 自己検出のしくみ（`github.workflow_ref`）

reusable workflow から自リポジトリを checkout するとき，オーナー名やブランチをハードコードすると「フォーク利用者がワークフロー本体を書き換える」必要が出る．これを避けるため，GitHub Actions が提供する `github.workflow_ref` コンテキストから自分の場所を動的に取得する．

`github.workflow_ref` の値例：

```
tomio2480/github-workflows/.github/workflows/markdown-lint.yml@refs/heads/main
```

`@` 手前をスラッシュで分解すると `OWNER/REPO/PATH`，`@` 以降が ref になる．ワークフロー内の `Detect self repository and ref` ステップで以下を取得する．

表 1: 自己検出で得られる値

| 変数 | 値の例 | 用途 |
|---|---|---|
| `SELF_REPO` | `tomio2480/github-workflows` | 設定 checkout の `repository:` |
| `SELF_REF` | `refs/heads/main` / `refs/tags/v1` | 設定 checkout の `ref:` |

`inputs.central-ref` で明示的に上書きもできる（テストや過去バージョンを意図的に参照したい場合）．

これにより **フォーク運用者は reusable workflow 本体を触らなくてよい**．`alice/github-workflows` から呼び出されれば `alice/github-workflows` の設定が，`bob/github-workflows@v2` から呼び出されれば `bob/github-workflows@v2` の設定が自動で使われる．

## 📁 設定ファイルの解決順序

`Resolve config file paths` ステップは以下のロジックで config パスを決める．

表 2: 解決対象ファイルと解決ロジック

| ファイル | 解決順序 |
|---|---|
| `.markdownlint-cli2.yaml` | ① caller root に存在すれば採用 → ② 中央の `templates/.markdownlint-cli2.yaml` |
| `.textlintrc.json` | 同上 |
| `prh.yml` | 同上 |

**ファイル全置換方式** のため，caller に置いたファイルは中央と差分マージされず単独で採用される．部分的に中央を流用したいときは中央の該当ファイルを丸ごとコピーしてから改変する．

### textlint 用 runtime config 生成

`.textlintrc.json` の `rules.prh.rulePaths` は相対パスで書かれている．中央の textlint config と caller の prh.yml（または逆）を組み合わせると相対解決が意図どおりにならない場合がある．

このため workflow は次のステップを挟む．

1. 解決済みの textlint config を読み込む
2. `rules.prh.rulePaths` を解決済みの prh.yml の絶対パスで上書きする
3. `.textlintrc.runtime.json` として caller root に書き出す
4. textlint action にはこの runtime config を渡す

これにより override 組み合わせ（caller 辞書＋中央 textlintrc など）でも path が破綻しない．

## 🐶 reviewdog の挙動

表 3: reviewdog の主要パラメータ

| パラメータ | デフォルト | 意図 |
|---|---|---|
| `reporter` | `github-pr-review` | PR レビューコメントとして投稿．要 `pull-requests: write` |
| `level` | `warning` | PR 上では目立つが check 失敗扱いにはしない |
| `fail_on_error` | `false` | CI を常に緑にする．Bot 型運用の核 |
| `filter_mode` | `added` | PR で追加・変更された行にのみコメント．既存ファイル一斉指摘を防ぐ |

`filter-mode` を `nofilter` にすれば既存ファイルの全指摘が PR に流れる．棚卸し用の一時的設定として caller 側で上書き可能．

`reporter` を `github-check` に切り替えれば PR でないイベント（push など）でも lint 結果を check として表示できるが，本リポジトリのデフォルトは `github-pr-review` のみ対応．push 起動で lint したい場合は caller 側で `on: push` トリガーを追加し，本 reusable workflow を改修するか caller 内で処理を書くことになる．

## 🔀 caller → reusable → reviewdog のデータフロー

1. caller の `.github/workflows/md-lint.yml` が `workflow_call` で本 reusable を呼び出す
2. reusable 側の job 内で使う `GITHUB_TOKEN` は **caller のジョブトークン**（本リポジトリのトークンではない）．reviewdog が PR コメントを投稿する先は caller の PR
3. reusable 側の `permissions: contents: read, pull-requests: write` は caller から継承される．caller 側で `permissions:` を明記しないと reviewdog がコメント投稿権限を得られず失敗する
4. reviewdog action は内部で `github-pr-review` reporter を使い，PR number とトークンから REST/GraphQL で review comment を投稿する

## 🧪 トラブルシューティング

表 4: よくある失敗と対処

| 症状 | 原因 | 対処 |
|---|---|---|
| reviewdog がコメントを投稿しない | caller 側の `permissions: pull-requests: write` がない | caller workflow に `permissions` ブロックを追加 |
| 設定ファイルが見つからない旨のエラー | override ファイル名の typo | `.markdownlint-cli2.yaml` / `.textlintrc.json` / `prh.yml` の正確な名前を確認 |
| 既存ファイルで PR が指摘で埋まる | `filter-mode` が `nofilter` になっている | デフォルト `added` に戻すか caller 側で明示 |
| third-party action が動かない | SHA が古くアーカイブされた | Dependabot PR を確認して最新 SHA に更新 |
| self-lint が動かない | 本リポジトリ自体では reusable を呼び出していない | 必要なら別 caller workflow を本リポジトリに追加する |
