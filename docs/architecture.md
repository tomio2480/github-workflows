# 🧩 アーキテクチャ

## 要約

本リポジトリの composite action（v2 以降）の連携を説明する．対象は caller リポジトリ・中央リポジトリ・reviewdog で，PR へ inline コメントを付ける流れを扱う．あわせて `$GITHUB_ACTION_PATH` を起点とする自己検出（OWNER 非依存）を説明する．設定ファイルの解決順序，override のしくみ，テスト戦略も明らかにする．

## 目次

- 🗺 全体の流れ
- 🔍 自己検出のしくみ（`$GITHUB_ACTION_PATH`）
- 📁 設定ファイルの解決順序
- 👀 review 開始の可視化（PR reaction）
- 🐶 reviewdog の挙動
- 📝 lint summary コメントの投稿
- 🔀 caller → composite action → reviewdog のデータフロー
- 🔁 caller テンプレートの構造変更が伝播しない問題
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
  │ 2. uses: OWNER/github-workflows/.github/actions/markdown-lint@<SHA> # v2.2.0
  ▼
composite action（本リポジトリ）
  │ 1. PR に 👀 reaction を付け「review 開始」を可視化（`pull_request` イベント時のみ）
  │ 2. $GITHUB_ACTION_PATH から中央 templates の絶対パスを解決
  │ 3. caller root に config があれば優先，無ければ中央 templates/ を採用
  │ 4. scripts/generate-textlint-runtime.py で prh の絶対パスを埋め込んだ
  │    .textlintrc.runtime.json を生成
  │ 5. config に outputFormatters があれば除去した markdownlint runtime config を生成
  │ 6. Node.js setup
  │ 7. lint 依存（markdownlint-cli2・textlint 一式）を lockfile から tmpdir へ install
  │ 8. markdownlint-cli2 を実行（markdownlint-report.txt．summary 集計と共用）
  │ 9. レポートを errorformat で reviewdog へ渡す → PR レビューコメント
  │ 10. textlint を実行 → reviewdog で PR レビューコメント
  │ 11. 件数を集計して PR に summary コメントを upsert（hidden marker）
  ▼
PR の該当行に inline コメントが付き，summary コメント 1 件が PR timeline に
upsert される
lint 指摘では job を失敗させない（fail_on_error: false）．設定解決・setup 等の実行エラーは通常どおり失敗する
```

上図の `OWNER` は利用する中央リポジトリのオーナーに置換する．tomio2480 を直接利用する場合は `tomio2480`，フォーク運用では自分の GitHub ユーザー名．`<SHA>` は利用したい commit．バージョンコメント `# v2` を併記すると Dependabot が SHA とバージョンを自動追随する．

<!-- 図表キャプションは体言止めとするため，キャプション行のみ許容する（Issue #57 の方針）．以降の表も同様． -->
<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: 参照方式ごとの挙動

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 参照形式 | 挙動 | 推奨用途 |
|---|---|---|
| `@<SHA> # v2` | 指定 SHA を参照．Dependabot が SHA とバージョンを更新 PR で起票 | 既定．推奨 |
| `@main` | main の最新 commit を参照．中央の辞書・ルール更新が次回 PR から即反映．Dependabot 追随なし | 即時反映を優先する個人運用 |
| `@<SHA> # v2.0.0` | 不変．パッチ追随も止めて完全固定 | 完全再現性が必要な CI |
| `@v1` / `@v1.0.0` | self-detection bug により動作しない（v1 系は reusable workflow 形式） | 利用しない |

## 🔍 自己検出のしくみ（`$GITHUB_ACTION_PATH`）

composite action から中央 templates にアクセスする場面を考える．オーナー名やブランチをハードコードすると，「フォーク利用者が action 本体を書き換える」必要が出る．これを避けるため，`github.action_path`（環境変数 `$GITHUB_ACTION_PATH`）から自分のチェックアウト先絶対パスを取る．この値は GitHub Actions が composite action に提供する．そこからの相対参照で中央 templates にアクセスする．

`$GITHUB_ACTION_PATH` の値例（runner 上）を示す．

```text
/home/runner/work/_actions/tomio2480/github-workflows/<sha>/.github/actions/markdown-lint
```

action.yml は `.github/actions/markdown-lint/` に置かれている．このため `${GITHUB_ACTION_PATH}/../../../` がリポジトリルートになる．さらに `templates/` を結合すれば中央 templates ディレクトリが得られる．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2: 自己検出で得られる値

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 変数 | 値の例 | 用途 |
|---|---|---|
| `$GITHUB_ACTION_PATH` | `/.../tomio2480/github-workflows/<sha>/.github/actions/markdown-lint` | リポジトリルート起点 |
| `${GITHUB_ACTION_PATH}/../../../templates` | 同上 + `templates/` | 中央 templates 絶対パス |
| `${GITHUB_ACTION_PATH}/../../../scripts` | 同上 + `scripts/` | 抽出済みスクリプトの絶対パス |

`actions/checkout` での中央 repo の二重取得は不要．caller workflow 側で caller repo を 1 度だけ checkout すればよい．composite action は，GitHub Actions が自動展開した自リポジトリ全体にアクセスできる．

これにより **フォーク運用者は composite action 本体を触らなくてよい**．`alice/github-workflows@<sha>` からの呼び出しでは `alice/github-workflows` の templates が使われる．`bob/github-workflows@<sha>` なら `bob/github-workflows` の templates になる．

## 📁 設定ファイルの解決順序

`Resolve config file paths` ステップは以下のロジックで config パスを決める．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 3: 解決対象ファイルと解決ロジック

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| ファイル | 解決順序 |
|---|---|
| `.markdownlint-cli2.yaml` | ① caller root に存在すれば採用 → ② 中央の `templates/.markdownlint-cli2.yaml` |
| `.textlintrc.json` | 同上 |
| `.textlintignore` | 同上．textlint には `--ignore-path` で明示的に渡す |
| `prh.yml` | 同上 |
| `.textlint-allowlist.yml` | ① caller root に存在すれば絶対パスを採用 → ② 無ければ空文字（中央フォールバックを持たない optional ファイル．v2.1〜） |
| `.prh-extra.yml` | 同上（optional．v2.7〜）．存在すれば中央 prh 辞書に加算する追加辞書として渡す |

上 4 行は **ファイル全置換方式** のため，caller に置いたファイルは中央と差分マージされず単独で採用される．部分的に中央を流用したいときは中央の該当ファイルを丸ごとコピーしてから改変する．

`.textlint-allowlist.yml` と `.prh-extra.yml` は規約から外れる．
`scripts/resolve-config-path.sh` の「無ければ中央テンプレを返す」抽象には乗らない．
そのため `action.yml` 内で `[ -f <file> ]` を inline 判定する．
allowlist は存在すれば runtime config の `filters.allowlist` に inject される．
無ければ中央 `templates/.textlintrc.json` 既定の `"allowlist": {}`（noop）が使われる．
`.prh-extra.yml` は存在すれば `rules.prh.rulePaths` の 2 本目として追加される．
無ければ `rulePaths` は解決済み `prh.yml` の 1 本のみで従来どおり動く．

### lint 対象外パターンと self-test

中央 `templates/.markdownlint-cli2.yaml` の `ignores` は `tests/fixtures/` を既定で除外する．`templates/.textlintignore` も同様である．これは **故意に違反を含む fixture が caller PR レビューに大量の指摘として流れ込むのを防ぐ** ためである．`ignores` は CLI で明示 glob を渡しても適用される（明示 glob で fixture を指定しても ignore がかかれば 0 件になる）．

本リポジトリの自己統合テスト（`integration-action` job）を考える．composite action を fixture に対して実行し，指摘検出を確認する必要がある．そのためリポジトリルートに `.markdownlint-cli2.yaml` と `.textlintignore` の override を置く．caller-first 解決でこちらを優先採用させている．override 内容は中央 templates と同等で，`tests/fixtures/` の ignore のみ外している．caller 側で個別に fixture を ignore したくない場合も同じ手法を取ればよい．

### textlint 用 runtime config 生成

`.textlintrc.json` の `rules.prh.rulePaths` は相対パスで書かれている．
中央の textlint config と caller の prh.yml を組み合わせると相対解決が意図どおりにならない場合がある．
加えて caller の `.textlint-allowlist.yml` を `filters.allowlist` に inject する責務もここで担う．

このため workflow は次のステップを挟む．

1. 解決済みの textlint config を読み込む
2. `rules.prh.rulePaths` を解決済みの prh.yml の絶対パスで上書きする．
   caller root に `.prh-extra.yml` があれば `[prh.yml, .prh-extra.yml]` の 2 本にする（Issue #91）
3. caller root の `.textlint-allowlist.yml` があれば PyYAML で読み込み `filters.allowlist` を上書き．
   無ければ中央既定の `"allowlist": {}`（noop）が残る
4. `.textlintrc.runtime.json` として `RUNNER_TEMP` 配下に書き出す
5. textlint コマンドにはこの runtime config を渡す

allowlist の inject と追加辞書の加算は `scripts/generate-textlint-runtime.py` で行う．
argv 4 つ目（optional）で allowlist パスを，argv 5 つ目（optional）で追加辞書パスを受け取る．
argv 3 つの呼び出しは従来動作を厳密維持する．
PyYAML は遅延 import としており，3 つ呼び出しに依存追加を強要しない．

`textlint-rule-prh`（v6.1.0）は同一パターンの衝突を `rulePaths` の先頭側で解決する（実測）．
中央辞書を先頭に固定することで，caller の追加辞書は中央規則を上書きできず「足す」だけになる．
中央規則を変えたい caller は従来どおり `prh.yml` の全置換を使う．

PyYAML は `ubuntu-latest` runner に preinstall されている前提である．
再現性が必要な caller は `pyyaml-version` input にバージョン番号（例 `6.0.2`）を渡せばよい．
内部で `pip install pyyaml==<value>` として固定される．`==` 等の比較子は付けない．
既定（空文字）では何も install せず runner 既定の PyYAML を使う．

### `markdownlint` 用 runtime config 生成（`outputFormatters` の除去）

composite action は cli2 の既定 formatter 出力（`path:line[:col] RULE 説明`）に依存する．
依存箇所は reviewdog への errorformat 入力と summary 集計の 2 つである．
caller config が `outputFormatters` を定義すると既定 formatter は置き換えられる（併存しない）．
この場合，lint が走って違反があっても inline・summary とも 0 件になる（Issue #122）．

このため `scripts/generate-mdlint-runtime.py` が解決済み config を検査する．
`outputFormatters` キーがあるときだけ，除去済み runtime config を生成する．
生成先は src と同じディレクトリで，
名前は `.gh-workflows-runtime-*.markdownlint-cli2.yaml` の一意名とする．
除去した事実は `::warning::` アノテーションで caller に知らせる．
キーが無ければ何も生成せず，解決済みパスをそのまま cli2 へ渡す（パススルー）．

同じディレクトリへ置くのは相対パスの解決を保つためである（PR #129）．
`customRules` / `markdownItPlugins` 等は config ファイル基準で解決される．
一意名（`tempfile.mkstemp`）により caller 所有ファイルを上書きしない．
suffix は cli2 の `--config` が受理する規約に合わせる．
除去はトップレベルキーのテキスト除去で行い，他の行は保持する．
PyYAML（YAML 1.1）の往復では，引用符なしの `on` / `yes` 等が cli2 の
js-yaml 4 と異なる型へ化けて lint 挙動が変わりうるためである．
生成物は `markdownlint` 実行ステップが使用後に削除する（ワークスペース非汚染）．
独自 formatter が必要な caller は，本 action と別のワークフローで実行する．

この組み立てにより，override 組み合わせ（caller 辞書＋中央 textlintrc など）でも path が破綻しない．
caller 単独で固有名詞や法令名等の例外も差分追加できる．

## 👀 review 開始の可視化（PR reaction）

`pull_request` イベントで起動した場合，composite action は最初の step で PR 本文へ 👀 reaction を付与する．これは「workflow は起動済みで，これから lint review を行う」状態を示す．caller 側で即座に判別するための UX nicety である．reaction を付ける前に lint config 解決などで失敗した場合は reaction 自体が現れない．ただし reaction の API call が失敗した場合（後述の fail-open）も reaction は付かない．そのため「reaction 無し」だけで workflow 未起動かどうかは確定しない．最終的な切り分けは reviewdog コメントの有無や Actions の実行ログを併せて判断する．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 4: reaction による状態識別

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 状態 | 見え方 |
|---|---|
| reaction 無し | workflow 未起動，最初の reaction step より前で失敗，または reaction API 呼び出し失敗（fail-open のためレビューは継続し得る） |
| 👀 reaction あり | composite action が正常に動き始めた．以後 reviewdog の inline コメントを待つ |
| 👀 + reviewdog コメント | review 完了 |

GitHub API は同一 user × 同一 content の reaction を idempotent に扱う．そのため rerun や複数回実行でも reaction が重複生成されることはない．reaction の API call が失敗しても review 本体は続行する（fail open）．caller token に対する権限要件は既存の reviewdog コメント投稿と同じ `pull-requests: write` で十分．

## 🐶 reviewdog の挙動

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 5: reviewdog の主要パラメータ

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| パラメータ | デフォルト | 意図 |
|---|---|---|
| `reporter` | `github-pr-review` | PR レビューコメントとして投稿．要 `pull-requests: write` |
| `level` | `warning` | PR 上では目立つが check 失敗扱いにはしない |
| `fail_on_error` | `false` | lint 指摘では job を失敗させない．checkout や設定解決などの実行エラーは通常どおり失敗 |
| `filter_mode` | `added` | PR で追加・変更された行にのみコメント．既存ファイル一斉指摘を防ぐ |

`filter-mode` を `nofilter` にすれば既存ファイルの全指摘が PR に流れる．棚卸し用の一時的設定として caller 側で上書き可能．

`reporter` を `github-check` に切り替えれば，PR でないイベント（push など）でも lint 結果を check として表示できる．ただし本リポジトリのデフォルトは `github-pr-review` のみ対応．push 起動で lint したい場合は，caller 側で `on: push` トリガーを追加する．そのうえで本 composite action を改修するか，caller 内で処理を書くことになる．

`github-check` reporter を使う場合は追加権限が要る．caller workflow の `permissions` に **`checks: write` を追加** する．デフォルトの `github-pr-review` では `pull-requests: write` のみでよい．check 作成権限は別枠のため，付け忘れると権限エラーで失敗する．

## 📝 lint summary コメントの投稿

reviewdog の `github-pr-review` reporter は findings ゼロのとき何も投稿しない仕様である．このため PR を見たユーザーは「lint が走ったが指摘がなかった」のか「workflow が起動していない／失敗した」のかを判別できない．これを補うため composite action は最終 step で件数の summary コメントを 1 件 upsert する．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 6: summary コメントの仕様

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 項目 | 内容 |
|---|---|
| hidden marker | `<!-- gh-workflows-lint-summary -->`．他 bot（CodeRabbit / Gemini）と衝突しない `gh-workflows-` プレフィックス |
| 同定方法 | PR コメントを GET（pagination 対応）し marker を含むコメントを検索 |
| 動作 | 既存あり → PATCH，無し → POST．push のたびに同一コメントが最新化される |
| 表示内容 | 件数表（textlint は error / warning / info の内訳）と findings 上位 20 件の `<details>`，Actions run へのリンク．差分絞り込みが効いているときはリポジトリ全体の件数列を併記する（[Issue #104](https://github.com/tomio2480/github-workflows/issues/104)）．検査対象コミット（`Merge <head> into <base>` と base）も 1 行併記し，全体件数が古い base 由来かを summary 単体で判別できるようにする（[Issue #119](https://github.com/tomio2480/github-workflows/issues/119)） |
| 失敗時 | 必須 env 不足は execution error．API call 失敗は `::warning::` で annotation し exit 0（fail-open） |
| fork PR | `pull-requests: write` が降格されるため事前に skip．reviewdog inline コメントの制約と整合 |
| opt-out | composite action の `post-summary` input に `"false"` を渡せば投稿 step ごと skip．同一 PR で複数 job が同 marker を奪い合うケースの逃げ道．reviewdog の inline コメント投稿には影響しない |
| 件数フィルタ | composite action の `markdown-ignore` input に path glob を改行区切りで渡すと summary 件数から除外できる．`tests/fixtures/**` のような prefix 形式で相対・絶対両方のパスを除外する．reviewdog の inline コメントは `filter-mode` で別途制御されるため本 input の影響を受けない |
| 集計スコープ | summary の findings 一覧は PR 差分ファイルのみを対象にする（[Issue #59](https://github.com/tomio2480/github-workflows/issues/59)）．取得失敗時はリポジトリ全体スコープにフォールバックする．件数表には差分の件数と全体の件数を併記し，差分に現れない既存指摘の存在を可視化する（Issue #104） |

集計と投稿は責務分離して 2 つのスクリプトで実装される．[scripts/count-lint-findings.py](../scripts/count-lint-findings.py) は件数と findings 一覧を集計し，JSON を stdout に出す．入力は textlint の checkstyle XML（`textlint-report.xml`）である．加えて `markdownlint-cli2` のテキストレポート（`markdownlint-report.txt`）も読む．[scripts/post-lint-summary.sh](../scripts/post-lint-summary.sh) はその JSON を本文化して PR コメントを upsert する．`markdownlint` の実行は composite action 内の `markdownlint-cli2` 1 回である．結果テキストは reviewdog への入力（errorformat 経由の inline 投稿）と summary 集計で共用する．v2.11.0 で一本化した（[Issue #117](https://github.com/tomio2480/github-workflows/issues/117)）．

`markdown-glob`（既定 `**/*.md`）はリポジトリ全体を走査する．そのため textlint・`markdownlint` の実行結果自体は，リポジトリ全体分の findings を含む．reviewdog の `filter-mode`（既定 `added`）は **inline コメント投稿のみ** を diff 行に絞る機構である．summary 集計の対象範囲には影響しない．そのため対策前は「本 PR の差分ファイルは 1 件なのに summary は数百件」という事象が起きていた（Issue #59）．

対策として，composite action に `List PR diff files (for summary scoping)` step を追加した．[scripts/list-pr-diff-files.sh](../scripts/list-pr-diff-files.sh) が PR の差分ファイル一覧を取得する．API は `GET /repos/:owner/:repo/pulls/:pr/files` である．取得結果は `count-lint-findings.py` の `--diff-files-from` へファイルパスとして渡す．これにより summary は PR 差分ファイルのみを対象にする．GitHub API 呼び出しが失敗した場合は，`::warning::` を出しつつ `--diff-files-from` を渡さない．従来どおりリポジトリ全体スコープにフォールバックする（fail-open）．`--diff-files-from` は `count-lint-findings.py` 単体の後方互換を保つ．未指定時は従来どおりリポジトリ全体を対象にする仕様のままである．

reviewdog の `filter-mode: added`（既定）は PR 差分行に該当しない指摘を inline 化しない．このため「集計件数 N 件あるのに inline コメントが 0 件」という見え方が起こりうる．この差を埋めるため summary コメントには以下を含める．

- 文言で「inline 化されない指摘がある」旨を明示
- findings の上位 20 件を `<details>` で展開可能な形で列挙（file:line / severity / rule / message）
- Actions の workflow run へのリンク．`GITHUB_SERVER_URL` と `GITHUB_REPOSITORY` で URL の前半を組み立てる．`GITHUB_RUN_ID` と `GITHUB_RUN_ATTEMPT` で run 部分を続ける

これにより，filter-mode='added' で除外された指摘も PR コメントから直接辿れる．

同一 PR で複数の job が同じ marker で upsert すると race するため，integration テストは単一 job に絞る方針．caller 側で複数 job が並走する構成にしたい場合は別マーカー運用が必要（現状 input 化していないため job 分割は推奨しない）．

## 🔀 caller → composite action → reviewdog のデータフロー

1. caller の `.github/workflows/md-lint.yml` が `pull_request` などで起動する．job 内の step で本 composite action を `uses:` で呼び出す
2. composite action 内で使う GitHub token は，**caller が明示的に渡したトークン** である．受け口は `inputs.github-token` input で，通常は `${{ secrets.GITHUB_TOKEN }}` を渡す．composite action では `secrets.*` の自動継承が効かないため，input での受け渡しを要する．reviewdog が PR コメントを投稿する先は caller の PR
3. caller workflow 側には `permissions: contents: read, pull-requests: write` を明記する．明記しないと reviewdog がコメント投稿権限を得られず失敗する．また **外部フォークからの PR では reviewdog が inline コメントを投稿できない**．GitHub の制限で `GITHUB_TOKEN` が read-only になるためである．本プロジェクトは安全性の観点で `pull_request_target` を使わない方針のためである．詳細は [docs/security.md](security.md) を参照
4. reviewdog は `github-pr-review` reporter を使う．PR number とトークンから REST/GraphQL で review comment を投稿する

## 🔁 caller テンプレートの構造変更が伝播しない問題

`templates/.github/workflows/md-lint.yml` の構造変更は，既存 caller に
自動反映されない．対象は `concurrency` や `timeout-minutes` など，
workflow・job レベルのキーである．
Dependabot が追随するのは `uses:` の SHA とバージョンコメントのみである．
caller が自身の `.github/workflows/md-lint.yml` に書き写した内容までは
追わない．実測では 33 caller 中 32 件が，最新テンプレートの構造変更を
反映できていなかった．経緯は
[Issue #83](https://github.com/tomio2480/github-workflows/issues/83) を参照．

### composite action と reusable workflow の吸収範囲の違い

この限界は composite action（`markdown-lint`）固有のものである．
composite action は，caller の job 内の 1 ステップとして実行される．
そのため，自分を呼んだ job や workflow のキーを宣言できない．
対象は `concurrency`/`timeout-minutes`/`permissions` などである．
中央から効かせるには，caller のファイルを書き換える以外に方法がない．

一方 `claude-review`（v2.6〜）は reusable workflow 形式である．
`concurrency` と `timeout-minutes` は，中央だけで完結する．
持ち場は `.github/workflows/claude-review.yml` 側である．
caller は `uses:` の 1 行を更新するだけで恩恵を受けられる．

ただし `permissions` は reusable workflow でも例外であり，中央だけでは
完結しない．called workflow は `GITHUB_TOKEN` を昇格できないためである．
昇格できる範囲は，caller が与えた許可までに限られる．
`templates/.github/workflows/claude-review.yml` 自体が必要スコープを
宣言する設計を採るのは，この制約による．
将来 `claude-review` が新しい権限を要する機能を追加する場合，
reusable workflow 側の変更だけでは足りない．
caller 側の `permissions` ブロックの追記が別途必要になる．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 7: 変更が caller 側の作業を要するかどうか

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 変更の種類 | composite action（md-lint） | reusable workflow（claude-review） |
|---|---|---|
| 設定ファイル（`prh.yml` 等）の中身 | 中央だけで完結．caller 側の作業は不要 | 対象外 |
| action/workflow の inputs 追加（既定値あり） | 中央だけで完結 | 中央だけで完結 |
| `concurrency`/`timeout-minutes` 等，job・workflow レベルのキー | caller 側の書き換えが必要 | 中央だけで完結 |
| `permissions`（トークン権限） | caller 側の書き換えが必要 | caller 側の書き換えが必要（called 側は caller の許可を超えられない） |

job・workflow レベルの設定が要る新機能では，reusable workflow 形式を
優先検討する価値がある．
ただし `permissions` の追加は，どちらの形式でも caller 側の作業を
避けられない．

### 運用でのカバー

上記の限界を実装で解消できるまでの当面の運用は，次のとおりである．
詳細は [Issue #83](https://github.com/tomio2480/github-workflows/issues/83) を参照．

- caller 側の `.github/workflows/md-lint.yml` の書き換えを要する変更は，
  リリースノートに明示する．
  **caller 側対応の要否と，追記すべき内容** を GitHub Release に書く．
- 32 件の caller への backfill は，今回のセッションでは見送る．
  composite action が caller との構造差分を lint summary に注記する
  仕組み（Issue #83 案 2）も見送る．
  規模が大きいため，選択肢として Issue に残す．

## 🧪 テスト戦略

本リポジトリは composite action の品質保証として 3 層のテストを持つ．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 8: テスト 3 層

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 層 | 対象 | 道具 | 配置 | 実行 |
|---|---|---|---|---|
| 単体 | `scripts/` の Python / Bash ロジック | pytest / bats-core | `tests/python/` / `tests/bash/` | ローカル `pytest` / `bats`，CI の `unit-python` / `unit-bash` job |
| 統合 | composite action の step 連携 | `./.github/actions/markdown-lint` の local 参照 | `tests/fixtures/markdown/` + `.github/workflows/test-self-lint.yml` の `integration-action` job | CI で PR 起動時 |
| E2E | composite action から reviewdog 投稿まで | canary repo（picoruby-tea5767 等）からの実 PR | caller 側 | リリース前の手動確認 |

`scripts/` 配下にロジックを追加する際は test-first（Red → Green → Refactor）を守る．テストを通すためにテストを緩めない．

## 🧪 トラブルシューティング

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 9: よくある失敗と対処

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 症状 | 原因 | 対処 |
|---|---|---|
| reviewdog がコメントを投稿しない | caller 側の `permissions: pull-requests: write` がない，または `github-token` input を渡し忘れ | caller workflow に `permissions` ブロックを追加し，`with: github-token: ${{ secrets.GITHUB_TOKEN }}` を渡す |
| summary コメントが PR に出ない | fork PR からの起動，または summary 投稿 step が `::warning::` で fail-open している | 同一リポジトリの branch から PR を出し直す．Actions ログで warning メッセージを確認 |
| summary コメントが「指摘ゼロ」 のまま更新されない | 同 PR で複数 job が同じ marker を upsert していて race している | integration job を 1 本に絞るか別 marker 運用を検討 |
| PR に 👀 reaction が付かない | 上と同じく `pull-requests: write` 不足．または `pull_request` 以外のイベント（`push` 等）でトリガーされた | 権限を追加するか，`pull_request` ベースで起動する．reaction 失敗は warning に降格して review 自体は続行する |
| 外部フォークからの PR だけ reviewdog が投稿しない | GitHub の fork PR セキュリティ制限で `GITHUB_TOKEN` が read-only | 仕様．`pull_request_target` は供給網リスクから採用しない方針のため対処しない．base repo にブランチを切って PR を出し直せば投稿される |
| 設定ファイルが見つからない旨のエラー | override ファイル名の typo | `.markdownlint-cli2.yaml` / `.textlintrc.json` / `prh.yml` の正確な名前を確認 |
| `@v1` を pin した caller が `FileNotFoundError` で落ちる | v1 系（reusable workflow 形式）は self-detection bug により動作しない | v2 以降の composite action 形式へ移行する．caller を `@<SHA> # v2` 形式に書き換える |
| 既存ファイルで PR が指摘で埋まる | `filter-mode` が `nofilter` になっている | デフォルト `added` に戻すか caller 側で明示 |
| third-party action が動かない | アクションのリポジトリ削除や実行環境（Node.js バージョン等）の互換性欠如 | Dependabot PR を確認して最新 SHA に更新 |
| 統合テストが落ちる | `scripts/` の単体テストが先に落ちている可能性 | まず `pytest tests/python` と `bats tests/bash` を確認 |
