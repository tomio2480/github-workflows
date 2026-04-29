# 🧩 アーキテクチャ

## 要約

本リポジトリの composite action（v2 以降）が，caller リポジトリ・中央リポジトリ・reviewdog とどのように連携して PR に inline コメントを付けているかを説明する．`$GITHUB_ACTION_PATH` を起点とする自己検出による OWNER 非依存，設定ファイルの解決順序，override のしくみ，テスト戦略を明らかにする．

## 目次

- 🗺 全体の流れ
- 🔍 自己検出のしくみ（`$GITHUB_ACTION_PATH`）
- 📁 設定ファイルの解決順序
- 👀 review 開始の可視化（PR reaction）
- 🐶 reviewdog の挙動
- 🔀 caller → composite action → reviewdog のデータフロー
- 🧪 テスト戦略
- 🧪 トラブルシューティング

## 🗺 全体の流れ

図 1: PR 作成から PR コメントまでの流れ（データ flow）

```text
開発者
  │ git push + Pull Request 作成
  ▼
対象リポジトリ（caller）
  │ .github/workflows/md-lint.yml が on: pull_request で起動
  │ 1. actions/checkout で caller 自身を checkout
  │ 2. uses: OWNER/github-workflows/.github/actions/markdown-lint@<SHA> # v2
  ▼
composite action（本リポジトリ）
  │ 1. PR に 👀 reaction を付け「review 開始」を可視化（`pull_request` イベント時のみ）
  │ 2. $GITHUB_ACTION_PATH から中央 templates の絶対パスを解決
  │ 3. caller root に config があれば優先，無ければ中央 templates/ を採用
  │ 4. scripts/generate-textlint-runtime.py で prh の絶対パスを埋め込んだ
  │    .textlintrc.runtime.json を生成
  │ 5. Node.js setup
  │ 6. reviewdog/action-markdownlint → PR レビューコメント
  │ 7. textlint を tmpdir に install して実行 → reviewdog で PR レビューコメント
  ▼
PR の該当行に inline コメントが付く
lint 指摘では job を失敗させない（fail_on_error: false）．設定解決・setup 等の実行エラーは通常どおり失敗する
```

上図の `OWNER` は利用する中央リポジトリのオーナーに置換する．tomio2480 を直接利用する場合は `tomio2480`，フォーク運用では自分の GitHub ユーザー名．`<SHA>` は利用したい commit．バージョンコメント `# v2` を併記すると Dependabot が SHA とバージョンを自動追随する．

表 1: 参照方式ごとの挙動

| 参照形式 | 挙動 | 推奨用途 |
|---|---|---|
| `@<SHA> # v2` | 指定 SHA を参照．Dependabot が SHA とバージョンを更新 PR で起票 | 既定．推奨 |
| `@main` | main の最新 commit を参照．中央の辞書・ルール更新が次回 PR から即反映．Dependabot 追随なし | 即時反映を優先する個人運用 |
| `@<SHA> # v2.0.0` | 不変．パッチ追随も止めて完全固定 | 完全再現性が必要な CI |
| `@v1` / `@v1.0.0` | self-detection bug により動作しない（v1 系は reusable workflow 形式） | 利用しない |

## 🔍 自己検出のしくみ（`$GITHUB_ACTION_PATH`）

composite action から中央 templates にアクセスするとき，オーナー名やブランチをハードコードすると「フォーク利用者が action 本体を書き換える」必要が出る．これを避けるため，GitHub Actions が composite action に提供する `github.action_path`（環境変数 `$GITHUB_ACTION_PATH`）から自分のチェックアウト先絶対パスを取り，そこからの相対参照で中央 templates にアクセスする．

`$GITHUB_ACTION_PATH` の値例（runner 上）：

```text
/home/runner/work/_actions/tomio2480/github-workflows/<sha>/.github/actions/markdown-lint
```

action.yml は `.github/actions/markdown-lint/` に置かれているため，`${GITHUB_ACTION_PATH}/../../../` がリポジトリルート，さらに `templates/` を結合すれば中央 templates ディレクトリが得られる．

表 2: 自己検出で得られる値

| 変数 | 値の例 | 用途 |
|---|---|---|
| `$GITHUB_ACTION_PATH` | `/.../tomio2480/github-workflows/<sha>/.github/actions/markdown-lint` | リポジトリルート起点 |
| `${GITHUB_ACTION_PATH}/../../../templates` | 同上 + `templates/` | 中央 templates 絶対パス |
| `${GITHUB_ACTION_PATH}/../../../scripts` | 同上 + `scripts/` | 抽出済みスクリプトの絶対パス |

`actions/checkout` での中央 repo の二重取得は不要．caller workflow 側で 1 度だけ caller repo を checkout すれば，composite action は GitHub Actions が自動展開した自リポジトリ全体にアクセスできる．

これにより **フォーク運用者は composite action 本体を触らなくてよい**．`alice/github-workflows@<sha>` から呼び出されれば `alice/github-workflows` の templates が，`bob/github-workflows@<sha>` から呼び出されれば `bob/github-workflows` の templates が自動で使われる．

## 📁 設定ファイルの解決順序

`Resolve config file paths` ステップは以下のロジックで config パスを決める．

表 3: 解決対象ファイルと解決ロジック

| ファイル | 解決順序 |
|---|---|
| `.markdownlint-cli2.yaml` | ① caller root に存在すれば採用 → ② 中央の `templates/.markdownlint-cli2.yaml` |
| `.textlintrc.json` | 同上 |
| `.textlintignore` | 同上．textlint には `--ignore-path` で明示的に渡す |
| `prh.yml` | 同上 |
| `.textlint-allowlist.yml` | ① caller root に存在すれば絶対パスを採用 → ② 無ければ空文字（中央フォールバックを持たない optional ファイル．v2.1〜） |

**ファイル全置換方式** のため，caller に置いたファイルは中央と差分マージされず単独で採用される．部分的に中央を流用したいときは中央の該当ファイルを丸ごとコピーしてから改変する．

`.textlint-allowlist.yml` のみ規約から外れる．
`scripts/resolve-config-path.sh` の「無ければ中央テンプレを返す」抽象には乗らない．
そのため `action.yml` 内で `[ -f .textlint-allowlist.yml ]` を inline 判定する．
存在すれば runtime config の `filters.allowlist` に inject される．
無ければ中央 `templates/.textlintrc.json` 既定の `"allowlist": {}`（noop）が使われる．

### lint 対象外パターンと self-test

中央 `templates/.markdownlint-cli2.yaml` の `ignores` および `templates/.textlintignore` は `tests/fixtures/` を既定で除外する．これは **故意に違反を含む fixture が caller PR レビューに大量の指摘として流れ込むのを防ぐ** ためである．`ignores` は CLI で明示 glob を渡しても適用される（明示 glob で fixture を指定しても ignore がかかれば 0 件になる）．

本リポジトリの自己統合テスト（`integration-action` job）は composite action を fixture に対して実行して指摘検出を確認する必要があるため，リポジトリルートに `.markdownlint-cli2.yaml` と `.textlintignore` の override を置き，caller-first 解決でこちらを優先採用させている．override 内容は中央 templates と同等で，`tests/fixtures/` の ignore のみ外している．caller 側で個別に fixture を ignore したくない場合も同じ手法を取ればよい．

### textlint 用 runtime config 生成

`.textlintrc.json` の `rules.prh.rulePaths` は相対パスで書かれている．
中央の textlint config と caller の prh.yml を組み合わせると相対解決が意図どおりにならない場合がある．
加えて caller の `.textlint-allowlist.yml` を `filters.allowlist` に inject する責務もここで担う．

このため workflow は次のステップを挟む．

1. 解決済みの textlint config を読み込む
2. `rules.prh.rulePaths` を解決済みの prh.yml の絶対パスで上書きする
3. caller root の `.textlint-allowlist.yml` があれば PyYAML で読み込み `filters.allowlist` を上書き．
   無ければ中央既定の `"allowlist": {}`（noop）が残る
4. `.textlintrc.runtime.json` として `RUNNER_TEMP` 配下に書き出す
5. textlint コマンドにはこの runtime config を渡す

allowlist の inject は `scripts/generate-textlint-runtime.py` で行う．
argv 4 つ目（optional）で allowlist パスを受け取る．
argv 3 つの呼び出しは従来動作を厳密維持する．
PyYAML は遅延 import としており，3 つ呼び出しに依存追加を強要しない．

PyYAML は `ubuntu-latest` runner に preinstall されている前提である．
再現性が必要な caller は `pyyaml-version` input にバージョン番号（例 `6.0.2`）を渡せばよい．
内部で `pip install pyyaml==<value>` として固定される．`==` 等の比較子は付けない．
既定（空文字）では何も install せず runner 既定の PyYAML を使う．

この組み立てにより，override 組み合わせ（caller 辞書＋中央 textlintrc など）でも path が破綻しない．
caller 単独で固有名詞や法令名等の例外も差分追加できる．

## 👀 review 開始の可視化（PR reaction）

`pull_request` イベントで起動した場合，composite action は最初の step として PR 本文に 👀 reaction を付与する．これは「workflow は起動済みで，これから lint review を行う」状態を caller 側で即座に判別するための UX nicety である．reaction を付ける前に lint config 解決などで失敗した場合は reaction 自体が現れない．ただし reaction の API call が失敗した場合（後述の fail-open）も reaction は付かないため，「reaction 無し」だけで workflow 未起動かどうかは確定しない．最終的な切り分けは reviewdog コメントの有無や Actions の実行ログを併せて判断する．

表 4: reaction による状態識別

| 状態 | 見え方 |
|---|---|
| reaction 無し | workflow 未起動，最初の reaction step より前で失敗，または reaction API 呼び出し失敗（fail-open のためレビューは継続し得る） |
| 👀 reaction あり | composite action が正常に動き始めた．以後 reviewdog の inline コメントを待つ |
| 👀 + reviewdog コメント | review 完了 |

GitHub API は同一 user × 同一 content の reaction を idempotent に扱うため，rerun や複数回実行でも reaction が重複生成されることはない．reaction の API call が失敗しても review 本体は続行する（fail open）．caller token に対する権限要件は既存の reviewdog コメント投稿と同じ `pull-requests: write` で十分．

## 🐶 reviewdog の挙動

表 5: reviewdog の主要パラメータ

| パラメータ | デフォルト | 意図 |
|---|---|---|
| `reporter` | `github-pr-review` | PR レビューコメントとして投稿．要 `pull-requests: write` |
| `level` | `warning` | PR 上では目立つが check 失敗扱いにはしない |
| `fail_on_error` | `false` | lint 指摘では job を失敗させない．checkout や設定解決などの実行エラーは通常どおり失敗 |
| `filter_mode` | `added` | PR で追加・変更された行にのみコメント．既存ファイル一斉指摘を防ぐ |

`filter-mode` を `nofilter` にすれば既存ファイルの全指摘が PR に流れる．棚卸し用の一時的設定として caller 側で上書き可能．

`reporter` を `github-check` に切り替えれば PR でないイベント（push など）でも lint 結果を check として表示できるが，本リポジトリのデフォルトは `github-pr-review` のみ対応．push 起動で lint したい場合は caller 側で `on: push` トリガーを追加し，本 composite action を改修するか caller 内で処理を書くことになる．

`github-check` reporter を使う場合は caller workflow の `permissions` に **`checks: write` を追加** する必要がある．デフォルトの `github-pr-review` では `pull-requests: write` のみでよいが，check 作成権限は別枠のため付け忘れると権限エラーで失敗する．

## 🔀 caller → composite action → reviewdog のデータフロー

1. caller の `.github/workflows/md-lint.yml` が `pull_request` などで起動し，job 内の step で本 composite action を `uses:` で呼び出す
2. composite action 内で使う GitHub token は **caller が `inputs.github-token` 経由で明示的に渡したトークン**（通常は `${{ secrets.GITHUB_TOKEN }}` ）．composite action では `secrets.*` の自動継承が効かないため input で受け渡す必要がある．reviewdog が PR コメントを投稿する先は caller の PR
3. caller workflow 側に `permissions: contents: read, pull-requests: write` を明記しないと reviewdog がコメント投稿権限を得られず失敗する．また **外部フォークからの PR では GitHub の制限により `GITHUB_TOKEN` が read-only になり，reviewdog は inline コメントを投稿できない**（本プロジェクトは安全性の観点で `pull_request_target` を使わない方針のため．詳細は [docs/security.md](security.md) 参照）
4. reviewdog action は内部で `github-pr-review` reporter を使い，PR number とトークンから REST/GraphQL で review comment を投稿する

## 🧪 テスト戦略

本リポジトリは composite action の品質保証として 3 層のテストを持つ．

表 6: テスト 3 層

| 層 | 対象 | 道具 | 配置 | 実行 |
|---|---|---|---|---|
| 単体 | `scripts/` の Python / Bash ロジック | pytest / bats-core | `tests/python/` / `tests/bash/` | ローカル `pytest` / `bats`，CI の `unit-python` / `unit-bash` job |
| 統合 | composite action の step 連携 | `./.github/actions/markdown-lint` の local 参照 | `tests/fixtures/markdown/` + `.github/workflows/test-self-lint.yml` の `integration-action` job | CI で PR 起動時 |
| E2E | composite action から reviewdog 投稿まで | canary repo（picoruby-tea5767 等）からの実 PR | caller 側 | リリース前の手動確認 |

`scripts/` 配下にロジックを追加する際は test-first（Red → Green → Refactor）を守る．テストを通すためにテストを緩めない．

## 🧪 トラブルシューティング

表 7: よくある失敗と対処

| 症状 | 原因 | 対処 |
|---|---|---|
| reviewdog がコメントを投稿しない | caller 側の `permissions: pull-requests: write` がない，または `github-token` input を渡し忘れ | caller workflow に `permissions` ブロックを追加し，`with: github-token: ${{ secrets.GITHUB_TOKEN }}` を渡す |
| PR に 👀 reaction が付かない | 上と同じく `pull-requests: write` 不足．または `pull_request` 以外のイベント（`push` 等）でトリガーされた | 権限を追加するか，`pull_request` ベースで起動する．reaction 失敗は warning に降格して review 自体は続行する |
| 外部フォークからの PR だけ reviewdog が投稿しない | GitHub の fork PR セキュリティ制限で `GITHUB_TOKEN` が read-only | 仕様．`pull_request_target` は供給網リスクから採用しない方針のため対処しない．base repo にブランチを切って PR を出し直せば投稿される |
| 設定ファイルが見つからない旨のエラー | override ファイル名の typo | `.markdownlint-cli2.yaml` / `.textlintrc.json` / `prh.yml` の正確な名前を確認 |
| `@v1` を pin した caller が `FileNotFoundError` で落ちる | v1 系（reusable workflow 形式）は self-detection bug により動作しない | v2 以降の composite action 形式へ移行する．caller を `@<SHA> # v2` 形式に書き換える |
| 既存ファイルで PR が指摘で埋まる | `filter-mode` が `nofilter` になっている | デフォルト `added` に戻すか caller 側で明示 |
| third-party action が動かない | アクションのリポジトリ削除や実行環境（Node.js バージョン等）の互換性欠如 | Dependabot PR を確認して最新 SHA に更新 |
| 統合テストが落ちる | `scripts/` の単体テストが先に落ちている可能性 | まず `pytest tests/python` と `bats tests/bash` を確認 |
