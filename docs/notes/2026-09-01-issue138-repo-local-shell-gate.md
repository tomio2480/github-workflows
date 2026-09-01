# 配布する gate を自リポジトリへ適用した記録

## 要約

Issue #138 で `bin/verify-shell.py` を追加し，中央リポジトリ自身のシェル資産を
ShellCheck・shfmt・PSScriptAnalyzer で検査するようにした．
実装そのものより，適用の過程で判明した 3 点に記録の価値がある．
整形規則の選び方，`.ps1` の文字符号化，Windows 環境での改行コードである．
あわせて「チェックが pass した」と「対象を検査した」を区別する方法を残す．

## 目次

- なぜ自リポジトリに適用していなかったか
- shfmt の整形規則は既存コードから逆算して選ぶ
- PSScriptAnalyzer の BOM 指摘は実害のある指摘だった
- CRLF は ShellCheck を全行で誤爆させる
- pass だけでは検査範囲がわからない
- 波及したドキュメントの齟齬

## なぜ自リポジトリに適用していなかったか

`test-self-lint.yml` は Shell quality の reusable workflow を
`verify-script: tests/fixtures/shell-quality/verify-shell.py` で呼んでいた．
これは toolchain と caller contract を検証する自己テストであり，設計どおりである．

一方で `docs/shell-quality.md` の導入節は，caller repo が
`bin/verify-shell.py` を用意して検査対象を決める設計としていた．
本リポジトリもシェル資産を持つ caller であるが，この gate を持たなかった．

「Reusable Shell quality workflow」というチェック名が PR に出ていたため，
追加したスクリプトが検査されたと読めてしまう点が問題の本体である．
チェック名は job の名前であって，検査範囲の説明ではない．

## shfmt の整形規則は既存コードから逆算して選ぶ

shfmt は既定でタブインデントかつ `case` 分岐を字下げしない．
既定のまま `-d` を掛けると，既存 6 ファイルすべてが差分として出る．

実測して規則を絞り込んだ結果，`-i 2 -ci` を採った．
既存コードのインデント幅（2）と `case` 分岐の字下げに一致する．
残る差分はリダイレクト前の空白とパイプ継続の書式だけとなり，5 ファイル
16 行の修正で収束した．

`-sr`（リダイレクト演算子の後ろに空白）を足すと `2> /dev/null` は保てる．
しかしヒアドキュメントが `<< 'PY'` へ変わり，パイプ継続も書き換わる．
差分が広がるため採らなかった．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. shfmt のオプション選択と差分規模

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| オプション | 残る差分 |
|---|---|
| 既定（タブ） | 全 6 ファイル |
| `-i 2` | `case` 分岐の字下げ＋リダイレクト |
| `-i 2 -ci` | リダイレクトとパイプ継続のみ（採用） |
| `-i 2 -ci -sr` | ヒアドキュメントとパイプ継続 |

整形ツールを後から入れるときは，既定値をそのまま受け入れない．
既存コードに合う設定を実測で探すほうが，差分もレビュー負荷も小さい．

## PSScriptAnalyzer の BOM 指摘は実害のある指摘だった

`bin/release-patch.ps1` に `PSUseBOMForUnicodeEncodedFile` が出た．
非 ASCII を含む `.ps1` に UTF-8 BOM が無い，という指摘である．

形式的な指摘に見えるが，実害がある．
`CLAUDE.md` は PowerShell 版の実行を
`powershell -ExecutionPolicy Bypass -File bin\<name>.ps1` と案内している．
この `powershell` は Windows PowerShell 5.1 であり，
BOM の無い UTF-8 を現在の ANSI コードページとして読む．
日本語のコメントと文字列リテラルが文字化けする．

ルールを抑制せず BOM を付けた．指摘の背景を確認してから判断した結果である．

## CRLF は ShellCheck を全行で誤爆させる

Windows の `core.autocrlf=true` 環境では worktree が CRLF になる．
この状態で ShellCheck を実行すると，全行に SC1017（Literal carriage return）が
出て gate をローカル実行できない．リポジトリの blob は LF なので CI では起きない．

当初は git の管理下から LF で取り出して検査する回避を試したが，
毎回その手順を踏むのは現実的ではない．`.gitattributes` を追加し，
`*.sh` と `*.ps1` を `eol=lf` に固定した．

これは gate の副産物ではなく前提条件である．
ローカルで実行できない gate は，CI が落ちてから気づくことになる．

## pass だけでは検査範囲がわからない

ShellCheck と shfmt は成功時に何も出力しない．
そのため CI ログを見ても，対象を検査したのか対象が 0 件だったのかを区別できない．
チェックが緑であることは，検査したことの証明にならない．

gate の冒頭で対象一覧を出力するようにした．

```text
targets (shellcheck, shfmt): bin/release-patch.sh, scripts/add-pr-reaction.sh, ...
targets (PSScriptAnalyzer): bin/analyze-powershell.ps1, bin/release-patch.ps1
```

子プロセスの出力と混ざらないよう `flush=True` を付ける．
付けないと Python 側のバッファリングにより順序が入れ替わる．

同種の失敗は過去にもある．「lint の pass は指摘ゼロではない」という
`fail_on_error: false` の件と根が同じである．
自動化を足したら，何を検査したかがログから読めるかを併せて確認する．

## 波及したドキュメントの齟齬

gate の追加後にドキュメントを点検したところ，本件と無関係な古さも見つかった．

- `docs/architecture.md` のテスト層の表に静的解析層が無かった．
- `docs/setup-guide.md` が配置対象を「`scripts/` 配下のスクリプト 2 本」と
  書いていた．実際は 8 本である．同様に docs・templates のファイル数も古い．
- `README.md` のディレクトリ構成に `bin/` 全体と
  `scripts/list-pr-diff-files.sh` が無かった．

ファイル数の直書きは，追加のたびに必ず古くなる．
Issue #142 で版コメントについて出した結論と同じ構図である．
規律で守れない一致要求は，要求そのものを外す．
今回は数を書くのをやめ，README のディレクトリ構成を単一の情報源とした．

## 参照

- Issue #138，PR #146（v2.13.7）
- `docs/shell-quality.md`「中央リポジトリ自身の gate」節
- `docs/notes/2026-09-01-issue142-version-comment-major-only.md`
