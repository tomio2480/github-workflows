# 🖥 push 前ローカル Markdown lint

## 🎯 要約

`bin/lint-md.sh` は，中央リポジトリの設定を使って手元で Markdown を lint する．
各リポジトリへ linter を置かないため，中央の辞書やルールとずれない．
CI と同じ設定・同じ集計を通し，違いは終了コードだけである．
軽微な文体指摘のために CI を 1 巡させる無駄を減らす目的で用意した（Issue #134）．

## 🗺 目次

- 🧭 ねらい
- 🚀 使い方
- 🎯 検査対象の決まり方
- 🔍 CI との対応
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
| `<files...>` | 報告対象を直接指定する |

`--glob` は composite action の `markdown-glob` に当たる．
`--ignore-glob` は `markdown-ignore` に当たる．
caller 側で値を変えている場合は，同じ値を渡す．

`--glob` は報告対象の選定にも効く．
拡張子を `.md` 以外にした caller で，対象が 1 件も選ばれない事態を防ぐためである．
選定に使うのは拡張子だけで，ディレクトリ部は見ない．
絞り込みは後段の集計が行うため，多めに選んでも害はない．

終了コードは 3 通りである．

表 2. 終了コードの意味．

| コード | 意味 |
|---|---|
| 0 | 指摘なし．対象 0 件の場合を含む |
| 1 | 指摘あり |
| 2 | 実行失敗．設定不正・依存導入失敗・linter 自体の異常終了 |

## 🎯 検査対象の決まり方

引数でファイルを渡さない場合，基点との差分と untracked ファイルを対象とする．
基点は `--base` の指定を最優先とし，無ければ `@{upstream}`，`origin/main`，
`HEAD` の順で最初に解決できたものを使う．
push 前の検査では「push 先が既に持っている状態」が最も近い基点になるためである．

削除したファイルは対象から外す．実在しない path を linter へ渡さないためである．
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

設定の解決も composite action と同じ caller-first である．
呼び出し元に同名ファイルがあればそれを使い，無ければ中央 `templates/` を使う．
`.textlint-allowlist.yml` と `.prh-extra.yml` の加算も同じ扱いである．

意図的な違いは終了コードだけである．
CI の reviewdog は非ブロッキングで，指摘があっても job を失敗させない．
ローカルは指摘ありで 1 を返す．push 前に気づくためのゲートだからである．

## ⚡ 依存キャッシュ

lint 依存は `.github/actions/markdown-lint/package-lock.json` から導入する．
毎回 `npm ci` を走らせると，待ち時間が CI と変わらなくなる．
そのため `install-lint-deps.sh` の `LINT_DEPS_CACHE_DIR` で再利用する．

置き場所の既定は `${XDG_CACHE_HOME:-${HOME}/.cache}/github-workflows-md-lint` で，
`LINT_MD_CACHE_DIR` で変更できる．
鍵は manifest と lockfile の内容ハッシュのため，依存が変われば作り直される．
古い `node_modules` を掴む経路はない．

導入は専用ディレクトリで組み立て，完成後に鍵の位置へ 1 度の rename で移す．
同時に走った別プロセスへ未完成の状態を見せないためである．
競合に負けた場合は相手の成果を使い，自分の組み立て先を捨てる．
CI は同変数を渡さないため，runner 上は従来どおり 1 回限りの tmpdir を使う．

## 🪟 Windows での実行

Git Bash から実行する．PowerShell 版は用意していない．

```bash
bash /c/path/to/github-workflows/bin/lint-md.sh
```

Python は `python3` と `python` のうち，PyYAML を読み込めるほうを自動で選ぶ．
どちらも使えない場合は `pip install pyyaml` を促して終了する．

## 🪝 lefthook との併用

`templates/lefthook.yml` の既定は `npx` で linter を直接呼ぶ．
この形は中央設定を読まないため，CI と結果が一致しない．
中央設定での検査を hook へ載せる場合は，`run` を本スクリプトの呼び出しへ置き換える．
パスはリポジトリごとに異なるため，テンプレートには既定値を置いていない．

## 🧪 テスト

`tests/bash/lint-md.bats` は npm と linter を差し替え，全体の経路を検証する．
対象選定は `tests/bash/list-local-md-targets.bats` が受け持つ．
表示は `tests/python/test_render_local_lint_report.py` が受け持つ．
`bats tests/bash` と `python -m pytest tests/python` は CI でも実行される．
