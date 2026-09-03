# 2026-09-04 prh の `[object Object]` と辞書スキーマの境界

## 概要

`templates/prh.yml` の `JS` ルールの指摘へ `[object Object]` が付いていた．
原因は `specs` を `prh:` キーの下へ書いたことである．
`prh:` は prh 本体のスキーマに無く，`textlint-rule-prh` が
指摘メッセージ末尾へ文字列連結する自由記述であった．
表示のみの不具合だが，辞書の書き方の誤りとツールの不具合を利用者が区別できない．
本メモは原因の特定手順と，あわせて見つかった `release-patch.ps1` の
Windows PowerShell 5.1 での破綻を記す．

## 目次

- 🧭 原因の特定
- 🧪 実証の組み立て
- 🧱 スキーマ外キーという落とし穴
- 🪟 release-patch.ps1 が 5.1 で落ちる
- 🧹 ワークツリーの空実体
- 🔗 参照

## 🧭 原因の特定

`templates/prh.yml` 内で `prh:` キーを持つ 12 エントリのうち，
`JavaScript` だけが値をオブジェクト配列にしていた．他 11 は説明文の文字列である．

依存を読んで裏を取った．`prh` の `lib/raw.d.ts` の `interface Rule` に
`prh` フィールドは無い．未知のキーは `rule.raw` へ素通しされる．
`textlint-rule-prh` がそれをメッセージへ連結する．

```js
// node_modules/textlint-rule-prh/lib/textlint-rule-prh.js:131,229-230
const prh = diff.rule.raw.prh || null;
const suffix = prh !== null ? "\n" + prh : "";
const messages = actual + " => " + expected + suffix;
```

配列を `"\n" + prh` へ渡すため `[object Object]` になる．
推測で直さず実装を読んだことで，`prh:` を消すか `specs:` へ移すかの
判断根拠が得られた．

## 🧪 実証の組み立て

textlint の CLI は config の解決規則が絡み，最小再現に手間が掛かった．
`--no-textlintrc -c` を渡しても rules を読まない状態が続いた．

prh engine を直接叩く 20 行程度の script へ切り替えた．
`textlint-rule-prh` と同じ手順でメッセージを組み立てたところ，即座に再現した．

```text
===== 修正前 =====          ===== 修正後 =====
JS => JavaScript            JS => JavaScript
[object Object]             JS => JavaScript
JS => JavaScript            markdown => Markdown
[object Object]             diffs: 3
markdown => Markdown
diffs: 3
```

**知見**: lint ツールの表示を調べるとき，CLI 全体を再現する必要は無い．
表示を組み立てている層だけを取り出せば足りる．
`prh` の実体は `.github/actions/markdown-lint/node_modules` にある．
`createRequire` でそこから解決すれば，scratchpad の script からも使える．

## 🧱 スキーマ外キーという落とし穴

`prh` は未知のキーを黙って受け取る．誤りは lint の実行時まで表面化せず，
表面化しても「辞書が悪いのかツールが悪いのか」が読み取れない形で出る．

対策として回帰テストを 2 件足した．

- 全 rule の `prh:` が文字列であること．
- `JavaScript` rule の specs が `JS => JavaScript` と `JSON => JSON` を持つこと．

後者は prh の仕組みを利用している．prh は `from === to` の spec を
「変換されないことの assert」として辞書の読み込み時に検査する．
`JSON => JSON` を置くことで word boundary の効きが CI で守られる．

**知見**: 設定ファイルのスキーマが緩いとき，型の検査はテスト側で持つ．
値の正しさは対象ツール自身の自己テスト機構（prh なら `specs`）へ寄せる．
両者は役割が違うため，どちらか片方では足りない．

### 記述順への依存は無かった

`Node.JS` は `/[Nn]ode\.JS/` と `/\bJS\b/` の双方にマッチしうる．
`.` が非単語文字のため `\b` が成立するためである．

`Node.js` ルールを `JavaScript` より前へ移した版を作って比較した．
移動後に出現回数と前後関係を assert し，重複が混ざらないようにした．
結果は現状と同一で `Node.JS => Node.js` となり，
`JS => JavaScript` の diff は出ない．競合の解決は記述順に依存しない．

Codex のレビューは「major issues なし」で，挙げた 6 観点への個別回答は無かった．
未検証の観点が残ることになるため，本項は手元で確かめてから閉じた．

**知見**: bot レビューが「問題なし」を返しても，こちらが挙げた論点に
答えたことにはならない．論点ごとに決着を確認する．

## 🪟 release-patch.ps1 が 5.1 で落ちる

`v2.17.2` の発行時に判明した．`bin/release-patch.ps1` を
Windows PowerShell 5.1 で実行すると，`--dry-run` が途中で落ちる．

```text
[dry-run] git tag v2.17.2 bdcbc78...
[dry-run] git push origin v2.17.2
gh : release not found
At bin\release-patch.ps1:105 char:1
+ gh release view $Version *> $null
```

105 行は再実行時の冪等性のために Release の存在を確認する箇所である．
未作成なら `gh` が stderr を出すのは正常な経路である．
5.1 は `$ErrorActionPreference = 'Stop'` のもとで，native command の
stderr を終了エラーへ昇格させる．`*> $null` を書いても昇格が先に起きる．
`pwsh` 7 では同じ行が素通りし，最後まで完走した．

`CLAUDE.md` は PowerShell 環境の実行形を次のように案内している．

```text
powershell -ExecutionPolicy Bypass -File bin\<name>.ps1
```

この形は 5.1 を起動する．案内どおりに実行すると落ちることになる．

`tests/powershell/` に `release-patch.Tests.ps1` は無い（Issue #167）．
bash 版は `tests/bash/release-patch.bats` が 309 行で網羅している．
移植の食い違いを検出する手立てが無いという #167 の指摘が，
実際の破綻として現れた形である．

**知見**: 静的解析では捕まらない．5.1 と 7 の差は実プロセスを起動しないと出ない．
`.ps1` の振る舞いテストは，実行するシェルの版も込みで設計する必要がある．

## 🧹 ワークツリーの空実体

セッション開始時，`.claude/worktrees/awesome-feynman-9deda8` は空だった．
`git worktree list` にも載っていなかった．
`.gitignore` の `.claude/` 配下にあるため追跡もされない．

このディレクトリで `git` を実行すると，git は親へ遡って
本体リポジトリの `.git` を見つける．`git status` は「clean」を返し，
`git log` も本体の履歴を返す．ディレクトリが空でも成功するため，
出力だけでは異常に気づけない．

`ls` が 0 件を返したことで気づいた．同じパスへ `git worktree add` し直して復旧した．

**知見**: ワークツリーで作業を始める前に `git worktree list` で
実体の登録を確認する．`git status` の成功は，正しい場所にいることを意味しない．

## 🔗 参照

- Issue #174・PR #175
- Issue #167（`release-patch.ps1` の Pester テスト）
- Issue #66（`JS` ルールが略語の正当用法へマッチする事例）
- `docs/dictionary-maintenance.md`「prh.yml の書き方」
- `docs/notes/2026-05-03-prh-user-negative-lookahead.md`（同根の substring match 対策）
