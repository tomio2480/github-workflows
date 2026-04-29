# 🧠 開発メモ

## 要約

本リポジトリの実装・レビューを通じて得た知見をまとめる．
コード規律自体はリポジトリの [CLAUDE.md](../CLAUDE.md) と各自のグローバル設定に従う．
本ドキュメントでは中央リポジトリ特有の設計判断を扱う．
あわせて自動レビュー対応で繰り返し有効だったパターンも記録する．

PR #16 と #17 の経験を主な題材としている．
類似タスクに着手するセッションが過去判断を辿れるようにする．

## 目次

- 🧭 設計判断
- 📜 文章・コードの規約要点
- 🤖 自動レビュー対応のパターン
- 🛠 ローカル検証ワークフロー
- 🔁 PR push 後のポーリング運用
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

## 📂 主な参照先

- リポジトリ性格と AI 作業規律: [CLAUDE.md](../CLAUDE.md)
- アーキテクチャと自己検出ロジック: [docs/architecture.md](architecture.md)
- 採用ルールの根拠: [docs/rule-rationale.md](rule-rationale.md)
- 辞書と allowlist の使い分け: [docs/dictionary-maintenance.md](dictionary-maintenance.md)
- 公開運用の脅威モデル: [docs/security.md](security.md)
