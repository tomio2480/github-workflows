# 🧠 開発メモ

## 要約

本リポジトリの実装・レビューを通じて得た知見をまとめる．
コード規律自体はリポジトリの [CLAUDE.md](../CLAUDE.md) と各自のグローバル設定に従う．
本ドキュメントでは中央リポジトリ特有の設計判断を扱う．
あわせて自動レビュー対応で繰り返し有効だったパターンも記録する．

PR #16 と #17 の経験を主な題材としている．
PR #23 と #25 の経験で得た知見も追記している．
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

一方で `.textlint-allowlist.yml` は中央フォールバックを持たない optional ファイル．
`resolve-config-path.sh` には流用しない．
`action.yml` 内で `[ -f .textlint-allowlist.yml ]` を inline 判定する．
存在すれば絶対パスを，無ければ空文字を step output として渡す．

### 外部ツール依存は preinstall 前提＋ caller opt-in 固定

PyYAML は `ubuntu-latest` runner にプリインストール済のため，composite action の既定では何もしない．
caller が再現性を重視する場合のみ `pyyaml-version` input にバージョン番号（例 `6.0.2`）を渡す．
内部で `pip install pyyaml==<value>` として実行されるため，比較子の混入は厳禁．

description で `==` 等の指定子混入を許すと `pyyaml====6.0.2` のような無効指定を生む．
「バージョン番号のみ．== 等の比較子は付けない」と必ず明記する．

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

### markdownlint をローカルで再現

```bash
npx --yes markdownlint-cli2 <対象ファイル>
```

ただし `markdownlint-cli2` の最新版は composite action 内蔵版と差がある．
composite action は `reviewdog/action-markdownlint` を SHA pin している．
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

`v2` mutable を最新 patch に進める際は `git tag -f v2 <new-SHA>` と `git push -f origin v2` を使う．
ログには `forced update` と表示される．
新 SHA が古い SHA の祖先関係（fast-forward 可能な範囲）にあるため caller への破壊性は低い．
本リポジトリでは patch リリースごとに進めることを既定とし，pre-release 通知は不要としている．

### リリース後のフォローアップ運用

patch リリース直後には次の 3 領域のフォローアップを習慣的に実施する．

- 関連 Issue の判断記録：上流提案の要否，経緯保管庫としての open 維持判断
- 別リポジトリの meta Issue への観測材料コメント：直近の鮮度の高い指摘パターンを蓄積
- caller リポジトリの追従状況確認：並行セッションが走っている可能性を前提に網羅的に確認

各判断のヒューリスティックと標準手順は [docs/notes/2026-05-01-post-release-followup.md](notes/2026-05-01-post-release-followup.md) にまとめた．

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
- SemVer 移行の判断ログ: [docs/notes/2026-05-01-semver-release-operations.md](notes/2026-05-01-semver-release-operations.md)
- retroactive タグ発行手順: [docs/notes/2026-05-01-retroactive-tag-rollout.md](notes/2026-05-01-retroactive-tag-rollout.md)
- 全角記号スペース禁止の判断ログ: [docs/notes/2026-04-30-fullwidth-symbol-prh-rule.md](notes/2026-04-30-fullwidth-symbol-prh-rule.md)
