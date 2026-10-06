# 🖥 push 前ローカル Markdown lint

## 🎯 要約

`bin/lint-md.sh` は，中央リポジトリの設定を使って手元で Markdown を lint する．
caller 側の override を優先し，設定の解決と指摘の集計を CI と共用する．
中央 checkout と caller の pin，runtime の違いによる結果の差は残る．
軽微な文体指摘のために CI を 1 巡させる無駄を減らす目的で用意した（Issue #134）．

## 🗺 目次

- 🧭 ねらい
- 🚀 使い方
- 📦 要約と実行記録
- 🔬 実行条件と caller 宣言の照合
- 🎯 検査対象の決まり方
- 🔍 CI との対応
- ↩ 改行コードの扱い
- 🛑 突合できないときは止める
- ⚡ 依存キャッシュ
- 🪟 Windows での実行
- 🪝 lefthook との併用
- 🧪 テスト

## 🧭 ねらい

本リポジトリは「ローカル linter を持たずクラウド CI を正とする」方針を採る．
各リポジトリへ linter を配ると，中央設定との drift と重複メンテが生じるためである．

`bin/lint-md.sh` はこの方針を崩さない．置くのは中央 1 箇所だけで，
呼び出し元リポジトリには何も追加しない．
実行のたびに中央の `templates/` と `package-lock.json` をその場で読む．
中央側の辞書更新は，次回の実行から全リポジトリのローカル検査へ届く．

## 🚀 使い方

呼び出し元リポジトリの中で，中央リポジトリのチェックアウトを指して実行する．

```bash
bash /path/to/github-workflows/bin/lint-md.sh
```

主な指定は次のとおり．

表 1. `bin/lint-md.sh` の引数．

| 引数 | 働き |
|---|---|
| なし | 変更した Markdown だけを報告対象にする |
| `--all` | 追跡済みの Markdown をすべて報告対象にする |
| `--base <ref>` | 差分の基点を明示する |
| `--glob <pattern>` | lint 対象の glob を変える．既定は `**/*.md` |
| `--ignore-glob <pattern>` | 報告から除外する path を指定する |
| `--format full\|summary\|json` | 通常出力・要約・JSON を選ぶ．既定は `full` |
| `--limit <N>` | 要約・JSON に表示する指摘の上限．既定は 20 件 |
| `--output-dir <dir>` | 実行記録を保存する親ディレクトリを指定する |
| `<files...>` | 報告対象を直接指定する |

`--glob` は composite action の `markdown-glob` に当たる．
`--ignore-glob` は `markdown-ignore` に当たる．
caller 側で値を変えている場合は，同じ値を渡す．

`--glob` は報告対象の選定にも効く．
渡されたときは拡張子で絞らず，変更ファイルをすべて選ぶ．
glob の解釈を選定側で再実装すると，取りこぼす方向の穴が開き続けるためである．
選定は報告を絞り込む集合を作るだけで，指摘の発生源ではない．
多めに選んでも後段の集計が落とす．

`--glob` を渡さないときだけ，選定は `.md` 固定である．
既定の用途はこちらで，Markdown を触っていない push では linter を起動しない．
絞り込みは後段の集計が行うため，多めに選んでも害はない．

終了コードは 3 通りである．

表 2. 終了コードの意味．

| コード | 意味 |
|---|---|
| 0 | 指摘なし．対象 0 件の場合を含む |
| 1 | 指摘あり |
| 2 | 実行失敗．設定不正・依存導入失敗・linter 自体の異常終了 |

## 📦 要約と実行記録

AI が繰り返し使う場合は，`--format summary` または `--format json` を指定する．
件数と保存先を先に読み，個々の判断に必要な指摘だけを全文から確認できる．

```bash
bash /path/to/github-workflows/bin/lint-md.sh --format summary --limit 10
bash /path/to/github-workflows/bin/lint-md.sh --format json --output-dir /tmp/lint-runs
```

要約と JSON は，両 linter を合わせて既定 20 件まで表示する．
各メッセージは空白をまとめ，240 文字を超える部分を省く．
表示件数の上限は検査と集計に影響せず，省略件数を `display.omitted` に残す．
`--limit 0` は件数と保存先だけを読む用途に使える．

実行ごとに専用ディレクトリを作るため，前回の記録を上書きしない．
保存先の既定は OS の一時ディレクトリである．
`--output-dir` の相対パスは，呼び出したディレクトリを基準に解決する．
引数なしの通常出力は従来どおりで，記録を残さない．
`--format full --output-dir <dir>` では通常出力と全文保存を併用できる．

表 3. 実行記録の内容．

| ファイル | 内容 |
|---|---|
| `summary.txt` | 件数・指摘の抜粋・全文への参照 |
| `report.json` | `schema_version: 1` の実行結果と保存先 |
| `full.txt` | 通常出力の全文．指摘を省略しない |
| `diagnostics.log` | 標準エラー出力．選定した基点や実行失敗の原因 |
| `targets.txt` | 報告対象として選定したパス |
| `findings.json` | CI と共通の処理で集計した全指摘 |
| `markdownlint-report.txt` | `markdownlint` の元レポート |
| `textlint-report.xml`・`textlint-stderr.log` | textlint の元レポートと診断 |
| `install.log` | 依存導入のログ |
| `context.json` | 解決した設定の hash，runtime，caller の宣言との比較 |

途中で失敗した場合は，その段階までに作ったファイルだけが残る．
一時複製と runtime config は終了時に回収し，保存記録には含めない．
保存記録は自動削除しない．不要になったら保存先を削除する．

JSON の `status` は `ok`・`findings`・`not_applicable`・`error` のいずれかである．
終了コードは出力形式によらず表 2 のままとする．
実行失敗時の指摘件数は `null` とし，指摘なしの 0 件と区別する．
対象 0 件は `not_applicable` とし，linter を実行しない．
`coverage.selected` は報告対象の選定件数，`mirrored` は一時複製の件数である．
これらは linter が実際に検査した件数を示すものではない．
caller と中央リポジトリのルート・HEAD SHA も記録する．
設定の内容そのものは保存せず，`context.json` にパスと hash を残す．

要約・JSON の標準出力に診断ログは混ぜない．失敗時も保存先から読める．
引数不正，Git 管理外，Python 不在など，記録開始前の失敗は標準エラー出力で報告する．
この場合や保存先の作成に失敗した場合は，JSON を返せず終了コード 2 となる．
読み取り側は JSON の有無と終了コードの両方を確認する．

## 🔬 実行条件と caller 宣言の照合

記録を保存する実行では，設定の解決後，runtime config の生成前に条件を記録する．
終了時に読み直し，途中で変わった設定や依存 manifest があれば exit 2 にする．
選定段階の失敗や対象 0 件では，実行条件の収集へ進まない．

表 4. `context.json` の記録範囲．

| 項目 | 記録する事実 |
|---|---|
| `files` | resolver が選んだ設定，workflow，依存 manifest のパスと SHA-256 |
| `source` | 中央の HEAD・GitHub 上の repo 名・未コミット変更の有無 |
| `runtime` | PATH 上の Node の版と実行ファイル，実際の Python と PyYAML の版 |
| `selection` | ローカルへ渡した glob と ignore |
| `calls` | Markdown lint action の直接呼び出し，条件，公開 input と項目別の比較 |
| `unresolved_calls`・`workflow_errors` | 追跡していない呼び出しと解析できない workflow |
| `stability` | 収集直後の captured，終了確認後の stable，途中変更時の changed |

設定の選択は既存 resolver が担い，記録側では選び直さない．
raw byte の hash は途中変更の確認に使う．pin との内容比較では CRLF を LF に揃えた hash を使う．
未コミット変更は中央 checkout 全体の有無を示す．変更された内容は収集しない．
設定が外部ファイルや custom rule を参照していても，再帰的には追跡しない．
開始・終了間に変更して元へ戻した場合も検出対象外であり，file のロックは行わない．

caller の `.github/workflows/*.yml` と `.yaml` は PyYAML で読む．
YAML の `on` や版番号を真偽値・数値へ変換しない．
重複 key，merge key，複数 document，解析失敗は unknown として残す．
文字列内の `uses:` は呼び出しへ数えない．

中央の GitHub repo 名と一致する，40 桁 SHA の Markdown lint action 参照を照合する．
Node の既定 input と中央の設定・依存 manifest は，その pin の Git object から読む．
ネットワーク取得，checkout，pin 内のコード実行は行わない．
未取得 object，浮動 ref，式，reusable workflow の先，local action は unknown とする．
GitHub Actions の式を独自に評価しない．

Node は整数の major 指定または major.minor.patch の完全指定だけを比較する．
major の一致は patch の一致を意味しない．版の範囲や matrix の式は unknown になる．
glob は action が 1 つの引数としてそのまま渡すため，末尾の改行も含めて比較する．
ignore は action と同じ読み方に揃えて比較する．
改行で行に分けて空行だけを捨て，各行の前後の空白を除き，`\` を `/` に揃える．
ignore では，YAML のブロック形式（`|`）が付ける末尾の改行は一致の判定に影響しない．
空白だけの行を含む宣言は action が拒否するため，元の値のまま different と記録する．
どちらも，意味が等価かまでは判定しない．
比較できた ignore の `expected` と `actual` には，揃えた後の値を記録する．
caller 側の設定は caller_override と記録する．CI が checkout した設定との一致は保証しない．
token・env・secret は収集せず，公開 input は Node・glob・ignore の 3 項目に限る．

違いと unknown は lint 指摘から独立した情報であり，それだけでは lint の終了コードを変えない．
要約は比較件数と `context.json` のパスを示し，詳細を端末へ展開しない．
`report.json` の `context` は安定性と比較件数，`artifacts.context` は詳細の保存先を持つ．
各項目の same は，その項目の比較が一致したという意味に限る．
すべての CI 条件，検査対象，実行結果が一致したという証拠ではない．

## 🎯 検査対象の決まり方

引数でファイルを渡さない場合，基点との差分と untracked ファイルを対象とする．
基点は `--base` の指定を最優先とする．
無ければ `@{upstream}`，`origin/HEAD`，`origin/main`，`HEAD` の順で
最初に解決できたものを使う．
push 前の検査では「push 先が既に持っている状態」が最も近い基点になるためである．
`origin/HEAD` を見るのは，既定ブランチが `main` でないリポジトリのためである．
`HEAD` はコミット済みの変更を含まないため最後の手段とする．
選ばれた基点は実行のたびに `base = ...` として表示する．

対象から外すのは削除したファイルだけである．実在しない path を渡さないためである．
symlink が通常ファイルへ置き換わったような型変更は，中身が入れ替わるため含める．
選定の実体は `scripts/list-local-md-targets.sh` にある．

引数でファイルを渡した場合は，呼び出し時のカレント基準の指定を
リポジトリルート相対へ直してから集計へ渡す．
サブディレクトリからの相対指定や絶対指定でも，指摘が取りこぼされない．
実在しないファイルやリポジトリ外の path は，実行失敗として 2 を返す．
打ち間違いが「実在しない 1 件だけを対象にした」形になり，
全指摘が絞り込みで消えて 0 終了する事故を防ぐためである．

対象の選定に失敗した場合も 2 を返す．
存在しない ref を `--base` へ渡した打ち間違いが，
「対象 0 件」として lint を素通りする事故を防ぐためである．

## 🔍 CI との対応

lint そのものは composite action と同じく glob 全体へ掛ける．
caller 設定の glob 除外と `.textlintignore` は，glob 実行のときだけ効く．
変更ファイルだけを引数で渡すと，CI と結果がずれる．

対象ファイルへの絞り込みは，CI の summary と同じ `count-lint-findings.py` の
`--diff-files-from` に任せる．
ローカル専用の集計を書くと，同じレポートから違う件数の出る余地が残る．
表示だけを `scripts/render-local-lint-report.py` が担う．

対象の選定だけは CI と異なる．CI は PR の差分ファイル一覧を API から取るが，
ローカルは基点との 2 点比較である．
基点より進んだ変更が作業ツリーに無い場合，ローカルは多めに選ぶ．
報告が増える方向のずれであり，取りこぼしにはならない．

設定の解決も composite action と同じ caller-first である．
呼び出し元に同名ファイルがあればそれを使い，無ければ中央 `templates/` を使う．
`.textlint-allowlist.yml` と `.prh-extra.yml` の加算も同じ扱いである．

意図的な違いは終了コードだけである．
CI の reviewdog は非ブロッキングで，指摘があっても job を失敗させない．
ローカルは指摘ありで 1 を返す．push 前に気づくためのゲートだからである．

## ↩ 改行コードの扱い

linter を掛ける先は作業ツリーそのものではない．
対象ファイルを一時ディレクトリへ複製し，`\r\n` を `\n` へ寄せてから掛ける．
作業ツリーのファイルは書き換えない．改行の設定は利用者の環境に属するためである．
複製は `scripts/normalize-lint-targets.py` が作る．

理由は CRLF の作業ツリーで CI と結果が食い違うことにある（Issue #169）．
`ja-technical-writing/sentence-length` は文の字数を数える．
文が行をまたぐとき，行末の `\r` がその文の内側に入り 1 字ぶん多く数えられる．
80 字ちょうどの文が「81 字，Over 1 characters」として報告される．
CI は LF の checkout で走るため，同じ commit でも 0 件になる．

行末が `．` で終わる文では起きない．
文の切れ目のあとに来る `\r` は，次の文の先頭の空白として捨てられるためである．
そのため誤検出は「長い段落の途中で折り返した文」に偏る．

変換するのは `\r\n` の組だけである．単独の `\r` は改行ではないため残す．
消すと行が連結され，指摘が消えたり増えたりする．
末尾改行も足さない．`MD047` が末尾改行の有無を見るためである．

複製へ入れるのは検査対象のファイルだけである．
報告は `count-lint-findings.py` が対象ファイルへ絞るため，対象外の指摘は
元から捨てられている．
glob と `.textlintignore` はパスで効くため，複製が相対構造を保つかぎり
「glob 全体へ掛ける」という前節の対応は崩れない．

## 🛑 突合できないときは止める

textlint は checkstyle 出力へ絶対パスを書く．
集計は複製のルートを prefix として剥がし，リポジトリルート相対へ戻す．
剥がせなかったパスは対象一覧と一致せず，その指摘は捨てられる．
lint 自体は成功しているため，利用者には「指摘なし」の 0 終了として見える．

Windows では，大小文字・8.3 名・ジャンクションの解決有無で表記が割れうる．
そのため集計の前に `scripts/check-report-paths.py` で剥がせることを確かめる．
剥がせない絶対パスが 1 件でもあれば，実行失敗（終了コード 2）として止める．
黙って 0 件にするより，止めて気づかせる．そのほうが害は小さい．

## ⚡ 依存キャッシュ

lint 依存は `.github/actions/markdown-lint/package-lock.json` から導入する．
毎回 `npm ci` を走らせると，待ち時間が CI と変わらなくなる．
そのため `install-lint-deps.sh` の `LINT_DEPS_CACHE_DIR` で再利用する．

置き場所の既定は `${XDG_CACHE_HOME:-${HOME}/.cache}/github-workflows-md-lint` で，
`LINT_MD_CACHE_DIR` で変更できる．
鍵は manifest と lockfile の内容ハッシュのため，依存が変われば作り直される．
古い `node_modules` を掴む経路はない．

導入は専用ディレクトリで組み立て，完成後に鍵の位置へ移す．
同時に走った別プロセスへ未完成の状態を見せないためである．
公開先の確保は `mkdir` で行う．不可分な操作で，既にあれば失敗する．
競合に負けた場合，相手の公開が済んでいればその成果へ相乗りする．
済んでいなければ公開を諦め，自分の組み立て先をそのまま使う．
待たないのは，その時点で自分の導入が完了しているためである．
CI は同変数を渡さないため，runner 上は従来どおり 1 回限りの tmpdir を使う．

## 🪟 Windows での実行

Git Bash から実行する．PowerShell 版は用意していない．

```bash
bash /c/path/to/github-workflows/bin/lint-md.sh
```

Python は `python3` と `python` のうち，PyYAML を読み込めるほうを自動で選ぶ．
どちらも使えない場合は `pip install pyyaml` を促して終了する．

`core.autocrlf` が有効な作業ツリーでも，CI と同じ件数になる．
仕組みは「[改行コードの扱い](#-改行コードの扱い)」を参照する．

## 🪝 lefthook との併用

`templates/lefthook.yml` の既定は `npx` で linter を直接呼ぶ．
この形は中央設定を読まないため，CI と結果が一致しない．
中央設定での検査を hook へ載せる場合は，`run` を本スクリプトの呼び出しへ置き換える．
パスはリポジトリごとに異なるため，テンプレートには既定値を置いていない．

## 🧪 テスト

`tests/bash/lint-md.bats` は npm と linter を差し替え，全体の経路を検証する．
複製の作り方は `tests/python/test_normalize_lint_targets.py` が受け持つ．
突合の検査は `tests/python/test_check_report_paths.py` が受け持つ．
対象選定は `tests/bash/list-local-md-targets.bats` が受け持つ．
表示は `tests/python/test_render_local_lint_report.py` が受け持つ．
`bats tests/bash` と `python -m pytest tests/python` は CI でも実行される．
