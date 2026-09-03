# 🧠 開発メモ

## 要約

本リポジトリの実装・レビューを通じて得た知見をまとめる．
コード規律自体はリポジトリの [CLAUDE.md](../CLAUDE.md) と各自のグローバル設定に従う．
本ドキュメントでは中央リポジトリ特有の設計判断を扱う．
あわせて自動レビュー対応で繰り返し有効だったパターンも記録する．

PR #16 と #17 の経験を主な題材としている．
PR #23 と #25 の経験で得た知見も追記している．
PR #28 の経験で得た「機械生成 Markdown と bot レビュー対応」の知見も追記している．
PR #30・#31 の dogfooding の経験から「scope 分割」「設計 pivot」「複数 reviewer 判断割れ」の知見も追記している．
PR #35 の prh 否定先読み修正と，Issue #34（SHA 直上バージョンコメント bump 漏れ再発防止）の知見も追記している．
PR #40 の textlint v15 互換性検証と，PR #43 の Gemini SHA 誤検知の知見も追記している．
Issue #157 で版コメントを行末スタイルへ統一した経緯も記録している．
類似タスクに着手するセッションが過去判断を辿れるようにする．

## 目次

- 🧭 設計判断
- 📜 文章・コードの規約要点
- 🤖 自動レビュー対応のパターン
- 🛠 ローカル検証ワークフロー
- 🔁 PR push 後のポーリング運用
- 🏷 リリース運用
- 🤝 サブエージェント委譲のサイクル
- 📂 主な参照先

## 🧭 設計判断

### 機能追加は argv の optional 化と遅延 import で後方互換を保つ

`scripts/generate-textlint-runtime.py` は当初 argv 3 つ厳格だった．
PR #17 で 4 つ目に optional の allowlist パスを受け取る形に拡張している．
要点は次のとおり．

- 受け入れ条件は `len(argv) in (3, 4)` で fail-fast
- 4 つ目が空文字または argv 3 つの呼び出しは従来動作を厳密維持
- 4 つ目専用の依存（PyYAML）は **遅延 import** にして既存 caller に依存追加を強要しない

caller の絶対多数は PR #17 以前の呼び出しを使う．
新機能を opt-in にする設計を採っている．

### 非 dict は silent overwrite せず TypeError で fail-fast

`rules` および `filters` が dict でない場合は意図的に `TypeError` を上げる．
PR #17 の Gemini review では「常に上書きする方が robust」という提案があった．
以下の観点で却下している．

- caller が `"filters": null` や `false` と書いた意図を silent overwrite で喪失するリスクが大きい
- 既存 `rules` のハンドリングと整合し，スクリプト全体で fail-fast 原則が一貫する

この strict 挙動は parametrize テストで pin 済である．
具体例は `test_allowlist_filters_non_dict_raises_type_error` を参照．

### 中央フォールバック有り / 無しでファイル検出ロジックを分ける

caller の override 対象ファイルは中央テンプレに同名ファイルが必ず存在する．
無ければ中央を使う規約のため `scripts/resolve-config-path.sh` で抽象化されている．

一方で `.textlint-allowlist.yml` と `.prh-extra.yml`（v2.7〜）は中央フォールバックを持たない．
optional ファイルのため `resolve-config-path.sh` には流用しない．
`action.yml` 内で `[ -f <file> ]` を inline 判定する．
存在すれば絶対パスを，無ければ空文字を step output として渡す．
`generate-textlint-runtime.py` 側は allowlist を 4 つ目，追加辞書を 5 つ目の引数で受ける．
どちらも空文字を「未設定」と解釈するため，action 側の分岐と 1 対 1 に対応する．

### 外部ツール依存は preinstall 前提＋ caller opt-in 固定

PyYAML は `ubuntu-latest` runner にプリインストール済のため，composite action の既定では何もしない．
caller が再現性を重視する場合のみ `pyyaml-version` input にバージョン番号（例 `6.0.2`）を渡す．
内部で `pip install pyyaml==<value>` として実行されるため，比較子の混入は厳禁．

description で `==` 等の指定子混入を許すと `pyyaml====6.0.2` のような無効指定を生む．
「バージョン番号のみ．== 等の比較子は付けない」と必ず明記する．

### 集計層と表示層を責務分離して機械生成 Markdown を作る

PR #28 で導入した summary コメント機構は集計と表示を分離して実装した．

- 集計：[scripts/count-lint-findings.py](../scripts/count-lint-findings.py) は raw な件数 / findings 一覧の JSON を出す
- 表示：[scripts/post-lint-summary.sh](../scripts/post-lint-summary.sh) の Python heredoc が担う．JSON を Markdown 本文に rendering する

表示用の正規化（path 相対化・rule prefix strip・改行畳み込み）は表示層に閉じる．
JSON 側は「集計の事実」として汎用に保つ．
将来別の出力先（Slack 等）を足すとき，集計層を再利用できる．

bats テストは fake curl + JSON fixture で書きやすい．
集計のロジックは pytest で網羅できる．
責務を分けるオーバーヘッドより，テスト容易性の利益が勝つ判断を採った．

### 集計件数と表示件数のギャップは UI 側で吸収する

reviewdog の `filter-mode: added`（既定）は PR 差分行に該当しない指摘を inline 化しない．
このため「summary が 13 件と表示するが inline コメントは 0 件」という見え方が起こりうる．

PR #28 では summary 本文を以下の構成にして「件数の意味」を明示した．

- 文言：「差分行に該当する指摘は inline，filter-mode で inline 化されない指摘は下記 details と Actions ログを参照」
- `<details>` 展開：findings 上位 20 件を file:line / severity / rule / message 形式で列挙
- 末尾：Actions workflow run へのリンク

集計件数と表示件数にギャップが出る UI を設計するときは「件数の意味」と「漏れた分の参照経路」を本文に組み込む．
数字だけ見せると利用者は「何が見えていないか」を判断できない．

ただしこのとき組み込んだ「Actions ログを参照」は実在しない経路だった．
個別の指摘は reviewdog へ渡るだけで，ログには rule ID とファイル名のどちらも出ない．
v2.14.0（Issue #148）で生レポートを artifact として配布する経路へ差し替えた．
参照経路を案内するときは，その経路を 1 度実際にたどって実在を確かめる．
詳細は [docs/notes/2026-09-01-issue148-lint-report-artifact.md](notes/2026-09-01-issue148-lint-report-artifact.md) を参照．

### 独立した変更は scope を割って小刻みに進める

PR #30 と PR #31 は連続した狙いを持つが，scope を分けた．
前者は v2.4.0（`post-summary` opt-out）である．
後者は v2.5.0（`markdown-ignore` + dogfooding workflow）である．

判断軸は次のとおり．

- v2.4.0 は self-test の summary 競合を予防する基盤．caller 形式の md-lint.yml を入れる前段として独立して価値がある
- v2.5.0 は応用層．`markdown-ignore` の設計と dogfooding workflow 追加が同時並行する規模．レビュー観点も多い
- 1 本の PR にまとめると change 量が膨らみ，レビューサイクルも長引く．2 段に分けると Red-Green の単位が小さくなり bot レビューの指摘も焦点が絞れる

scope の境界判定は **「単独で価値が生まれるか」** を基準にする．
v2.4.0 単独でも「self-test の race 整理」として merge 可能だった．
そのまま放置せずに v2.5.0 で応用層を載せた経緯となる．

### プランは investigation 後に再評価する．動かして判明する制約は素直に受け入れる

PR #31 の当初計画では `markdown-glob` を multi-line（改行区切り）へ拡張する案だった．
そこへ `#tests/fixtures/**` を混ぜる想定である．
着手後，`reviewdog/action-markdownlint` への配列展開が YAML expression では困難だと気付いた．
そこで **`markdown-ignore` 別 input** へ変更した．

教訓は次のとおり．

- プラン段階では実装上の制約をすべて把握できないことが多い
- investigation で前提の崩れを発見したら設計を pivot させる．計画書に固執しない
- 動かしてから判明する制約を素直に受け入れる．記録は judgment log に残す

詳細は [docs/notes/2026-05-02-v2.5.0-postmortem.md](notes/2026-05-02-v2.5.0-postmortem.md) を参照．

### upsert + hidden marker は単一プロセスで使う前提

[scripts/post-lint-summary.sh](../scripts/post-lint-summary.sh) は marker 付きコメントを upsert する．
marker は `<!-- gh-workflows-lint-summary -->` である．
動作は GET → 既存あり PATCH，無し POST である．
`gh-workflows-` プレフィックスで他 bot（CodeRabbit / Gemini）と衝突しない．

落とし穴は同一 PR で複数 job が同 marker を使うときの race である．
PR #28 の計画段階では，`integration-action-clean-only` job で指摘ゼロケースを別 job として目視確認する案があった．
途中で race の懸念に気付き drop した．
代替として「指摘ゼロ」ケースは pytest / bats で網羅した．

upsert + 単一 marker は前提として「同一スコープで 1 プロセスだけ書く」を要求する．
matrix や複数 job を導入する設計では marker をスコープ別に分けるか upsert を諦める．

詳細な判断ログは [docs/notes/2026-05-02-lint-summary-comment.md](notes/2026-05-02-lint-summary-comment.md) を参照．

## 📜 文章・コードの規約要点

`templates/.textlintrc.json` の合算で次が必須となる．

| 項目 | 設定 |
|---|---|
| 句点 | `．` （ja-no-mixed-period の periodMark） |
| 1 文の長さ | 80 字以内（sentence-length max 80） |
| 連続漢字 | 6 字以内（max-kanji-continuous-len max 6） |
| 全角カッコ `（）` `「」` | 前後にも内側にも半角スペースを入れない（ja-no-space-around-parentheses） |
| inline code span | 前後に半角スペース（ja-space-around-code） |
| 強調 `**` | 開始の直前と終了の直後に半角スペース．内側にスペースは入れない |

慣習として通っているもの（既存パターンに合わせる）．

- table caption（`表 N: ...`）は句点を付けない
- 助詞の前後に inline code を置く際は code span のスペース規則を優先する
- 図がある場合は図番号と alt 相当の要約を直下または直前に書く

Python テストの規約は次のとおり．

- 関数 docstring は **書かない**．テスト名と module docstring で意図を表現する
- `pytest.raises(..., match=...)` の `match` は具体的な部分一致を指定する
- 引数のバリエーションは `@pytest.mark.parametrize` で網羅する
- `tests/python/requirements.txt` は最小（`pytest`，必要に応じて `pyyaml`）

CodeRabbit の Docstring Coverage 既定しきい値 80 % は本スタイルでは満たせない．
テストファイル間の一貫性を優先する判断を採っている．

## 🤖 自動レビュー対応のパターン

### 採用 / 却下の判断軸

| 指摘パターン | 既定方針 |
|---|---|
| 仕様・後方互換の盲点（quoted form / コメント付き形式 等） | 採用 |
| description やコメントの誤読リスク指摘 | 採用 |
| robustness を理由とした silent overwrite 提案 | 設計と整合するか確認．本リポジトリは fail-fast 採用 |
| 既存パターンを 1 箇所だけ変える refactor | scope 外として follow-up issue 化 |
| inline shell の抽出提案 | 規模を見て判断．glue 程度なら抽出しない |

### 返信は決定と理由を明示する

bot レビューでも，採用 / 却下の決定と理由を明文化して返信する．
将来同様の指摘が来たときに過去の判断を辿るためのトレーサビリティになる．
scope 外の指摘は follow-up issue を起票して返信本文にリンクする．
具体例として PR #17 から Issue #18 を起票したケースがある．

### 設計意図はテストで pin する

「この挙動は意図的か？」という疑義が来るたびに「はい意図です」と答えるのは弱い．
設計意図を示す parametrize テストを足し，将来の不用意な silent overwrite 化を機械的に防ぐ．

PR #17 の `test_allowlist_filters_non_dict_raises_type_error` は具体例である．
filters 非 dict ケースとして None / False / list 2 種 / string / int の 6 通りを網羅し pin した．

### 構造アサーションでも TDD は成立する

PR #16 の `test_templates_prh.py` は YAML をパースしていない．
`templates/prh.yml` の生テキストを正規表現で走査する．
bare `JS` パターンの不在と `/\bJS\b/` の存在をアサートしている．
新規依存を増やさず Red→Green を回せた事例である．

regex は最初 `^\s*-\s*JS\s*$` だったが，レビューで次の漏れが指摘された．

- 末尾コメント `- JS  # 略称` 形式（Gemini）
- YAML quoted form `- "JS"` / `- 'JS'`（CodeRabbit）

最終形は `r"^\s*-\s*(?:['\"])?JS(?:['\"])?\s*(?:#.*)?\s*$"` となった．
構造アサーションは依存を抑えられる代わりに **想定パターンの網羅** を意識する必要がある．

### partial accept の返信は分けて根拠を述べる

PR #23 / #25 では Gemini と CodeRabbit から多項目を含む 1 コメントが届く場面に遭遇した．
単一コメント内で採用と却下が混在するケースもある．
返信草案を作る際は採用分と却下分を分けて記述し，却下分は 2-3 文で具体的な根拠を述べる．

例：PR #25 の Gemini #3172199229 は次の構造だった．

- 採用：「patch tag 更新」を「タグの更新」に変更
- 却下：`@<SHA> # v2.2.0` のバッククォート除去

却下の理由は次のように述べた．
同表内の他行（`@main` / `@v2 major mutable` / `@v2.2.0 patch immutable`）も同形式でバッククォートを使用している．
ここだけ除去すると当該行のみ書式が崩れる．
書式の一貫性を優先する判断基準を明示することで，bot に同種の指摘を繰り返されないようにする狙いもある．

### bot レビューが古い commit を見るパターンの返信定型

複数回 push する PR では，bot の指摘が「既に対応済み」のケースが頻発する．
PR #28 では同パターンが 1 件発生した．
返信は次の構造で書くと相手と将来の自分の双方が辿りやすい．

- 冒頭：先行対応済みである旨と該当 commit SHA
- 中段：実装の場所（ファイル + 関数名）と test の場所
- 末尾：「最新 commit 以降を確認してほしい」旨

定型化すると返信草案を `review-responder` agent で量産できる．
採用 / 却下とは別軸の「先行対応済」という第 3 の返信パターンとして明示する．

### 複数 reviewer の判断割れは decision log に残す

self-reviewer agent と Gemini で，同じコードに対する判断が割れる場合もある．
PR #31 では `_path_matches_ignore` の `endswith("/" + prefix)` 分岐の必要性で割れた．

- self-reviewer：「findings は常にファイル path だから dead」→ 削除推奨
- Gemini：「docstring 網羅性と防御性から残すべき」→ 復活推奨

最終判断は docstring 整合と防御性を優先して Gemini 案を採った．
削除の直後，復活させる流れとなった．commit 履歴には「削除 → 復活」の往復が残った．

採用 / 却下とは別軸の **「複数 reviewer 間の判断割れ」を 4 つ目の対応形態** として明示する．
returned commit message と返信に「どちらの観点を優先したか」と「直前の自己判断と異なる結論にした理由」を残すと往復を抑えられる．
将来同種の指摘が来たときにこの decision log を参照して即決できる．

### bot 定番指摘は既存スクリプトのスタイル踏襲で先回り潰しする

新規スクリプトを書くときは [scripts/add-pr-reaction.sh](../scripts/add-pr-reaction.sh) などの既存実装と同じ規律を踏襲する．

- 一時ファイルは `mktemp` + `trap 'rm -f ...' EXIT`
- curl は `--retry 2 --retry-all-errors --max-time 10`
- 必須 env 不足は execution error．API call 失敗は `::warning::` で fail-open

これらは Gemini が同種コードに毎回出してくる定番指摘である．
PR #28 でも mktemp / trap / retry 系の指摘は来なかった．
都度の指摘を後から潰すより，先回りでレビューサイクルを節約する方針が効く．

機械生成 Markdown 固有の sanitization 規律は，本リポジトリ単独では先回りしきれない観点である．
内容は改行・パイプ・絶対パス・フレームワーク内部 prefix の正規化である．
[tomio2480/settings#28](https://github.com/tomio2480/settings/issues/28) に meta Issue として起票した．
code-quality Skill / implementer prompt 側で先回りする方針とした．

### prh の pattern 合成挙動による落とし穴

prh は同一 rule 内の複数 pattern を内部で alternation に合成して `/g` 適用する．
PR #23 で `[/ X/, /X /]` のように leading / trailing を分けて書いた．
prh が `/(?: X|X )/gmu` に合成し，両側スペース入力で後続スペースを取りこぼして spec test が落ちた．

長い順 alternation `/ +X +| +X|X +/` を 1 本書くことで leftmost-longest を機能させる必要がある．
詳細は [docs/notes/2026-04-30-fullwidth-symbol-prh-rule.md](notes/2026-04-30-fullwidth-symbol-prh-rule.md) を参照．

## 🛠 ローカル検証ワークフロー

ドキュメント変更を含む PR では，push 前に次を流すと CI レビューサイクルを節約できる．

### Python ユニットテスト

```bash
python -m pytest tests/python -q
```

### textlint をローカルで再現

`templates/.textlintrc.json` の `rules.prh.rulePaths` は相対パスである．
ローカル実行時は絶対パスに差し替えた runtime config を作って渡す．

```python
import json, pathlib
cfg = json.loads(pathlib.Path('templates/.textlintrc.json').read_text(encoding='utf-8'))
cfg['rules']['prh']['rulePaths'] = [str(pathlib.Path('templates/prh.yml').resolve())]
pathlib.Path('.textlintrc.runtime.json').write_text(
    json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8'
)
```

実行例は次のとおり．

```bash
npx --yes -p textlint@14 \
    -p textlint-rule-preset-ja-technical-writing \
    -p textlint-rule-preset-ja-spacing \
    -p textlint-rule-prh \
    -p textlint-filter-rule-comments \
    -p textlint-filter-rule-allowlist \
    -- textlint --config .textlintrc.runtime.json <対象ファイル>
rm .textlintrc.runtime.json
```

### `markdownlint` をローカルで再現

```bash
npx --yes markdownlint-cli2 <対象ファイル>
```

ただし `markdownlint-cli2` の最新版は composite action 内蔵版と差がある．
composite action は `package-lock.json` で固定した `markdownlint-cli2` を実行する．
v2.11.0 で reviewdog 経路も cli2 へ統一した（Issue #117）．
Issue #121 で floating semver の `npx` 実行から lockfile 管理へ移行した．
固定中のバージョンは
[.github/actions/markdown-lint/package.json](../.github/actions/markdown-lint/package.json)
を参照する．
新しい rule（例 MD060）が最新版で追加されていることがある．
**新規エラーが自分の変更で発生したか既存 baseline かを切り分け**て扱う．
迷ったら `git stash` で変更を退避して baseline を確認するとよい．

## 🔁 PR push 後のポーリング運用

bot レビュー（Gemini Code Assist / CodeRabbit）の到着には数分から十数分の幅がある．
連続で push せず一拍おく狙いとして次の運用が有効である．

1. push 直後に baseline を取得する．2 つは排他的に異なるコメント種別を返す

    ```bash
    # inline review comments（特定行に紐づくレビューコメント）
    gh api repos/<owner>/<repo>/pulls/<n>/comments --paginate > .pr_inline_baseline.json
    # top-level / issue-level comments（PR スレッド全体への投稿）
    gh pr view <n> --json comments > .pr_top_baseline.json
    ```

2. Claude Agent SDK の `ScheduleWakeup` で初回 10 分後にチェック，以後 5 分ごとに polling
3. baseline と diff して新規コメント検出時にループ終了

`ScheduleWakeup` の自己再投入で polling は成立する．
prompt にループ全文を渡せばよい．
キャッシュ TTL の関係で 5 分間隔は厳密には非効率である．
bot レビューは到着間隔が読めないため受容している．

新規コメント検出後は次の順で対応する．

1. 採用と却下を決め，理由をまとめる
2. 採用分はローカルで修正＋テストして commit を分ける
3. ユーザー承認 → push
4. 全コメントに返信．scope 外の指摘は follow-up issue を起票してリンクで応答

### CI checks の監視は `bin/watch-pr-checks.{sh,ps1}` に任せる

`gh pr checks <n> --watch` を push 直後に実行しても監視にならない．
checks が未登録の時点では「no checks reported」を返して即座に終わる．
さらに `gh` 側の PR head は push へ数十秒遅れる場合がある．
1 つ前の commit の run を掴んだまま全 pass を返した実例が PR #159 にある．
いずれも「CI green」の誤認を生む（Issue #133）．

`bin/watch-pr-checks.sh` は `--watch` を使わず，状態を自前で polling する．
`--watch` は完了までブロックし，中断の手立てを持たない．
タイムアウトを効かせるには，待つ側が制御を握っている必要がある．

まず監視対象 commit の正を `git ls-remote` が返す実体とし，
`gh` の `headRefOid` がそこへ追いつくまで待つ．
問い合わせ先は head の所属先である．fork からの PR では head ブランチが
`origin` に無く，同名のブランチが base にあると無関係な commit を掴む．
`isCrossRepository` で判定し，fork なら head リポジトリの URL へ引く．

この分岐はレビュアーの判断が割れた箇所である．
Codex は「解決しないと無関係な commit を掴む」として追加を求めた．
Fable は削除を求めた．理由は 3 つである．
本リポジトリが fork PR をマージしないこと．`--expect-sha` で代替できること．
private fork の認証という失敗面を持ち込むこと．
残す判断を採った．理由は失敗の出方である．
削除した場合の失敗は「静かに待ち続ける」であり，
本スクリプトが防ごうとしている誤認そのものだからである．
スクリプト自体も特定リポジトリ専用ではない．

`--timeout` は監視全体に掛かる．段ごとに締切を取り直すと合計が 2 倍に
なりうるため，締切は 1 度だけ決めて両方の待機で使い回す．
次に checks の状態を間隔ごとに取り，完了の条件を 4 つ課す．
1 件以上あること，pending が無いこと，件数が前回の照会から変わっていないこと，
変わらなくなってから `--settle` 秒が過ぎたことである．

後ろの 2 つは，登録の時刻が workflow ごとに異なるためである．
ここは実害から学んだ箇所なので，経緯を残す．
当初は「前回の照会から増えていない」だけを条件にしていた．
本リポジトリでは CodeRabbit の status が push 直後に付き，
workflow の登録は約 1 分後であった．
その結果，CodeRabbit だけを見て「1 件が全 pass」と報告した．
実際には CI がまだ 1 つも起動していない．
自作の監視ツールが，防ごうとした false green を自ら出した．

据え置きの長さを 1 間隔でなく秒数とし，
その間ずっと件数が動かないことを要求する形へ変えた．
既定は観測した遅延の 2 倍である 120 秒とする．
等倍では，手前の待機が短い日に余裕が消える．

それでも `--settle` より後に現れる check は追えない．
そこまで要る場合は GitHub 側の required checks 設定で担保する．
本リポジトリの `main` に required checks は設定していない．
逃げ道は現状 `--settle` を伸ばすことだけである．

教訓は「静かであること」と「出そろったこと」は別だという点にある．
観測の間隔が短いと，前者を後者と読み違える．

`skipping` の扱いも同じ筋で決めた．
path filter で飛ばした check を通過件数へ数えず，`(N skipped)` として別に示す．
「検査した」と「検査を飛ばした」を報告で同じにしない．
すべて skip なら通過は 0 件のため，`no checks ran` と出す．
「all 0 checks passed」と書くと，path filter の設定ミスが green として沈黙する．

判定の材料は出力だけとし，`gh` の終了コードは見ない．
`gh pr checks` は pending で exit 8，failure でも非 0 を返しつつ結果を出す．
終了コードで判定すると，検査中の PR を照会失敗と誤読する．

監視の後には head が動いていないことを確かめる．
Issue #133 は「掴んだ run の `headSha` を照合する」と書いている．
本実装は監視の前後で `headRefOid` が変わらないことの確認で代えた．
監視対象の commit は 1 つに固定してあり，
その間に head が動かなければ，見ていた結果はその commit のものだからである．

```bash
bash bin/watch-pr-checks.sh 165
```

```powershell
powershell -ExecutionPolicy Bypass -File bin\watch-pr-checks.ps1 -Pr 165
```

終了コードは 4 種類である．

- `0`: 監視対象 commit で全 checks が pass した（すべて skip の場合を含む）
- `1`: 入力エラー・環境エラー
- `2`: タイムアウト，または監視対象 commit の不一致
- `3`: checks が pass しなかった

待っても成立しない状態を成功へ落とさない設計とした．
タイムアウトは非 0 で終え，直前の `gh` の stderr を添える．
認証切れが単なるタイムアウトに見える経路を残さないためである．

報告には必ず検査した commit を書く．
「全 pass」だけでは，どの commit を検査したのか読み取れない．

PowerShell 版は bats の対象にできないため，Pester で同じ観点をなぞる．
`tests/powershell/` に置き，repo-local gate（`bin/verify-shell.py`）が実行する．
スタブは PATH へ実行ファイルを置かず，同一セッションで `gh`・`git` の
関数を定義して覆う．関数の探索は呼び出し元まで遡るためである．
実行権限や拡張子に依存せず，Windows と Linux で同じ手順が使える．

## 🏷 リリース運用

### SemVer 風 patch tag 運用へ移行した

PR #25 でリリース運用を SemVer 風に統一した．
PR マージごとに `vX.Y.Z` patch タグを切り，`v2` major mutable も同時に最新 patch まで進める．
caller は次の 4 形態から選択できる．

- `@main`：即時反映．即時性優先
- `@v2` major mutable：patch リリースごとに自動追従
- `@v2.2.1` patch immutable：固定．新 patch への切り替えは caller の明示操作
- `@<SHA> # v2.2.1`：SHA pin．Dependabot がタグの更新を検知して PR を起票

詳細は [docs/notes/2026-05-01-semver-release-operations.md](notes/2026-05-01-semver-release-operations.md) を参照．

### retroactive にタグを切る場合の手順と落とし穴

過去の節目に retroactive で tag を切るケースは初期立ち上げ時に発生する．
PR #25 の作業時に v2.0.0/v2.1.0/v2.2.0/v2.2.1 を retroactive で発行した．
実行コマンドと落とし穴は [docs/notes/2026-05-01-retroactive-tag-rollout.md](notes/2026-05-01-retroactive-tag-rollout.md) に詳しく残してある．
代表的な落とし穴は `gh release create --target` が既存タグに使えない点である．

### mutable major の force-push は破壊的でない範囲で運用する

`v2` mutable を最新 patch に進める際は `git tag -f v2 <new-SHA>` で移動する．
push は `bin/release-patch.{sh,ps1}` に任せる（Issue #132）．
同スクリプトは remote の現在値が新 patch の祖先であることを確認し，
その観測値を `--force-with-lease` の期待値に置く．
並行リリースによる巻き戻りを防ぐためである．
ログには `forced update` と表示される．
新 SHA が古い SHA の祖先関係（fast-forward 可能な範囲）にあるため caller への破壊性は低い．
本リポジトリでは patch リリースごとに進めることを既定とし，pre-release 通知は不要としている．

### リリース後のフォローアップ運用

patch リリース直後には次の 3 領域のフォローアップを習慣的に実施する．

- 関連 Issue の判断記録：上流提案の要否，経緯保管庫としての open 維持判断
- 別リポジトリの meta Issue への観測材料コメント：直近の鮮度の高い指摘パターンを蓄積
- caller リポジトリの追従状況確認：並行セッションが走っている可能性を前提に網羅的に確認

各判断のヒューリスティックと標準手順は [docs/notes/2026-05-01-post-release-followup.md](notes/2026-05-01-post-release-followup.md) にまとめた．

### template バージョンコメント bump をチェックリスト化する

caller workflow のサンプルは `templates/.github/workflows/md-lint.yml` にある．
そこには `uses: ... @<SHA> # v2.x.y` 形式のバージョンコメントが入る．
release ごとにこれを更新する規律はあるが PR #28（v2.3.0）と PR #30（v2.4.0）の両方で更新漏れが Gemini に指摘された．
release 作業のチェックリストとして次を組み込む．

1. PR で release 予定のバージョンを確認する（minor / patch）
2. `templates/.github/workflows/md-lint.yml` の `# v2.x.y` を該当バージョンに揃える
3. 「v2.x.0+」のような未来形表記を残さない．明確な版指定にする

template バージョンコメントは「同 release で発行されるバージョン」を指すのが整合的である．
古いバージョンを残すと利用者が「新 input を持たない古い tag」を copy する事故につながる．
チェックリスト化の経緯と Gemini レビューの実例は [docs/notes/2026-05-02-v2.5.0-postmortem.md](notes/2026-05-02-v2.5.0-postmortem.md) を参照．

この規律は Issue #142 で撤回した．
`templates/` を触らないリリースが 1 回起きるたび，版コメントは 1 世代ずれる．
チェックリストで一致を保つ運用は構造的に破綻する（実際に 4 回再発した）．
現在は版コメントを major のみ（`# v2`）とし，patch 番号を書かない．
これによりずれ自体が発生しない．経緯は
[docs/notes/2026-09-01-issue142-version-comment-major-only.md](notes/2026-09-01-issue142-version-comment-major-only.md)
を参照．

### 版コメントを行末スタイルへ統一した理由

Dependabot が書き換えるのは SHA と同じ行にあるコメントだけである．
SHA 直上へ置いたコメントは更新されない．PR #10 では `# actions/checkout v4.3.0` が
SHA 更新後も残置された．一方 PR #143 の差分では，行末コメントが SHA と同時に
書き換わっている．

```diff
-        uses: anthropics/claude-code-action@1f291e1cfe0f5fc21db2aef19af844591600ade7 # v1.0.206
+        uses: anthropics/claude-code-action@a874e9ecd7bb36efdad65429c6b35815f5a08f10 # v1.0.210
```

以前は直上行スタイルを許容し，Dependabot PR のレビューで版コメントを手で補正していた．
Issue #153 で composite action を走査対象へ入れた結果，補正が要る箇所は増えた．
そこで Issue #157 において直上行 8 箇所を行末スタイルへ移し，手動補正の工程を廃した．
コメントへ書く内容も版だけ（`# v7.0.1`）へそろえた．Dependabot が書き出す形と一致させ，
自動更新の結果と手書きが混ざらないようにするためである．

検査の対象は `.github/workflows/`・`.github/actions/`・`templates/` の 3 つである．
`docs/` は入れていない（Issue #160）．本ファイル上部の差分引用のように，
古い SHA と版を残すことに意味のある記述が含まれるためである．検査へ入れると
直しようのない指摘になる．オンボーディング手順も SHA を `git/refs/tags` から
変数へ解決する形であり，固定 SHA を書き下していない．`docs/` へ現役の pin を
書く必要が生じた時点で，引用と区別する方法とともに再検討する．

スタイルの逸脱は `tests/python/test_action_pins.py` が検出する．
行末コメントの欠落，版以外の記述，同じ SHA への異なる版表記の 3 つを見る．
SHA と版の対応そのものは上流へ問い合わせないと確かめられないため，
CI では検査していない．手で pin を写す場合は `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`
で突合すること．

この工程が消えたぶん，`self-reviewer` Skill の観点リストへ組み込む候補（Issue #34）も
対象が 1 つ減った．

統一の作業で得た知見は
[docs/notes/2026-09-02-issue156-157-pin-consistency.md](notes/2026-09-02-issue156-157-pin-consistency.md)
を参照．検査が「検出できない形」を取りこぼしていた経緯もそこに残している．

### caller 追従確認は並行セッションを前提にする

リリース後の caller 追従確認では，自分の知らないセッションで取り込み PR が走っている可能性を前提にする．
本セッションでも v2.2.2 タグ発行の数時間後に blog 系 2 リポジトリで並行セッションによる取り込み PR がマージ済みだった．
caller を網羅する `gh search code` と Dependabot 設定確認の実コマンドは notes 側に残してある．

## 🤝 サブエージェント委譲のサイクル

PR #23 / #25 を通じて確立した委譲パターン．
[CLAUDE.md](../CLAUDE.md) と `model-orchestration` Skill の判定マトリクスに従う．

### PR 1 サイクルの典型的な委譲フロー

1. **計画段階**：Opus 自身で plan 立案．必要に応じて Plan agent で alternative 検討
2. **TDD Red**：Opus 直接（規模が小さければ）または `implementer`（sonnet）で test を書く
3. **TDD Green**：`implementer`（sonnet）で計画通りに実装
4. **ローカル検証**：Opus 直接で pytest / textlint / bats を回す
5. **セルフレビュー**：`self-reviewer`（sonnet）で `git diff origin/main...HEAD` の一次走査
6. **commit / push**：Opus 直接（最終判断）
7. **CI 待ち + bot レビュー収集**：`pr-context-collector`（haiku）でレビュー状況を構造化
8. **レビュー対応の方針決め**：Opus 自身が採用 / 却下を判断
9. **修正実装**：規模が大きければ `implementer`，小さければ Opus 直接
10. **返信草案**：`review-responder`（sonnet）で comment id 別に草案
11. **commit / push / 返信投稿**：Opus 直接
12. **Ready 直前**：`doc-syncer`（sonnet）でドキュメント整合性チェック
13. **マージ判断**：Opus 自身

### コンテキスト効率の判断

サブエージェントは独立サブタスクごとに新規スレッドで起動する．
1 PR 内に同種タスクが複数ある場合は，スレッド再利用より並列起動のほうがトークン効率は高くなる．

委譲先のモデルは `model-orchestration` Skill の表 2 に従う．
判断・最終決定・統合は Opus が握る．サブエージェントは草案・収集・抽出までを返す．

## 📂 主な参照先

- リポジトリ性格と AI 作業規律: [CLAUDE.md](../CLAUDE.md)
- アーキテクチャと自己検出ロジック: [docs/architecture.md](architecture.md)
- 採用ルールの根拠: [docs/rule-rationale.md](rule-rationale.md)
- 辞書と allowlist の使い分け: [docs/dictionary-maintenance.md](dictionary-maintenance.md)
- 公開運用の脅威モデル: [docs/security.md](security.md)
- textlint v15 互換性検証と Gemini SHA 誤検知: [docs/notes/2026-05-03-textlint-v15-compat.md](notes/2026-05-03-textlint-v15-compat.md)
- SemVer 移行の判断ログ: [docs/notes/2026-05-01-semver-release-operations.md](notes/2026-05-01-semver-release-operations.md)
- retroactive タグ発行手順: [docs/notes/2026-05-01-retroactive-tag-rollout.md](notes/2026-05-01-retroactive-tag-rollout.md)
- 全角記号スペース禁止の判断ログ: [docs/notes/2026-04-30-fullwidth-symbol-prh-rule.md](notes/2026-04-30-fullwidth-symbol-prh-rule.md)
- lint summary コメント機構の判断ログ: [docs/notes/2026-05-02-lint-summary-comment.md](notes/2026-05-02-lint-summary-comment.md)
- v2.4.0 / v2.5.0 dogfooding の判断ログ: [docs/notes/2026-05-02-v2.5.0-postmortem.md](notes/2026-05-02-v2.5.0-postmortem.md)
