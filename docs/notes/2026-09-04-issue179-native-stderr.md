# 🪟 native command の失敗を PowerShell でどう受けるか（Issue #179・#167）

## 🎯 要約

`bin/release-patch.ps1` が Windows PowerShell 5.1 で落ちる不具合を直した記録である．
原因は 5.1 が native command の stderr を終了エラーへ変えることであった．
共通ヘルパー `Invoke-NativeCommand` へ集約して抑えた．

調べる過程で，もっと大きな誤解が 1 つ見つかった．
`$ErrorActionPreference = 'Stop'` は fail-fast を保証しない．
PowerShell 7 は native command の非 0 終了で停止しない．
この誤解により，`git ls-remote` の失敗が沈黙する穴を 4 箇所つくっていた．
bash 版にも同じ穴があり，両版で塞いだ．

対応は PR #182．リリースは `v2.18.0`．

## 🗺 目次

- 🔥 何が起きたか
- 🧪 5.1 の破綻をどう再現するか
- 🧩 ヘルパーの設計
- 🕳 `Stop` は fail-fast を保証しない
- 📏 テスト設計で判断したこと
- 🧭 残した宿題
- 📎 参照

## 🔥 何が起きたか

`bin/release-patch.ps1` の 105 行が破綻点であった．

```powershell
gh release view $Version *> $null
if ($LASTEXITCODE -eq 0) {
```

Release 未作成なら `gh` は stderr へ書いて非 0 で終える．
終了コードで分岐する想定内の経路である．

Windows PowerShell 5.1 には昇格の癖がある．
`$ErrorActionPreference = 'Stop'` のもとで，
native の stderr を `ErrorRecord` へ変える．
変換はリダイレクトより先に起きる．`*> $null` を書いても抑えられない．

`CLAUDE.md` が案内する `powershell -ExecutionPolicy Bypass -File` は 5.1 を起動する．
**案内どおりに実行すると落ちる**という食い違いであった．

`v2.16.1` と `v2.17.2` の発行で 2 度踏んだ．
1 度目は作業メモへ回避策を書いて先へ進み，repo 側へ何も残さなかった．

## 🧪 5.1 の破綻をどう再現するか

**関数スタブでは再現できない．** ここが設計上の要点である．

既存の `tests/powershell/stub-runner.ps1` は，同一セッションで
`git`・`gh` の関数を定義して外部コマンドを覆う方式を採る．
実行権限や拡張子に依存しない．Windows と Linux で同じ手順を使える．

ただし，関数は native command として扱われない．
昇格は native command にだけ起きるため，この方式では再現できない．

そこで 3 段に分けた．表 1 に整理する．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1. 5.1 の破綻を検査する 3 つの層

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 層 | 方式 | どこで効くか |
|---|---|---|
| 機構の検査 | ヘルパー内で `$ErrorActionPreference` が緩んでいるか見る | 全環境 |
| 単体の回帰 | `powershell.exe` の子プロセスで実際の native command を呼ぶ | Windows のみ |
| 実体の回帰 | PATH へ `.cmd` スタブを置き，5.1 から本体を起動する | Windows のみ |

下 2 つは `powershell.exe` が無ければ飛ばす．CI は ubuntu のため走らない．
**CI 上で実質のゲートになるのは 1 段目だけ**である．
この非対称を承知の上で残した．判断は「残した宿題」に書く．

`.cmd` スタブは行末に敏感である．入れ子 `if` を 1 行で書き，
`.gitattributes` で CRLF 指定とした．

## 🧩 ヘルパーの設計

`bin/lib/native.ps1` へ `Invoke-NativeCommand` を置いた．

```powershell
$ErrorActionPreference = 'Continue'
$PSNativeCommandUseErrorActionPreference = $false

& $Command @ArgumentList
```

代入は関数スコープの局所変数を作る．
PowerShell の変数解決は呼び出し階層を遡るため，
`&` で呼ぶ scriptblock からこの値が見える．
関数を抜ければ消えるため，明示的な退避と復元は要らない．

`$PSNativeCommandUseErrorActionPreference` は 7.3 以降にのみ存在する．
5.1 では未定義の変数を作るだけで害が無い．

`-ArgumentList` を足したのは PSScriptAnalyzer のためである．
scriptblock 内の暗黙参照を `PSReviewUnusedParameter` は見通せない．
`bin/watch-pr-checks.ps1` の `ArgumentList` 無しの形が誤検出を招いた．

**知見**: 昇格の抑止に退避・復元は要らない．
局所変数を置くだけで足りる．手元で 5.1 と 7 の両方で確認した．

## 🕳 `Stop` は fail-fast を保証しない

Codex のレビューで受けた指摘が，当初の前提を崩した．

最初は「失敗をそのまま中断としたい呼び出しは直接呼びでよい」と書いた．
5.1 が昇格で止めてくれることを当てにした判断である．
これは 7 で成立しない．手元で確かめた結果を表 2 に示す．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2. `$ErrorActionPreference = 'Stop'` のもとでの native command の扱い

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 版 | stderr を出して非 0 で終える | 停止するか |
|---|---|---|
| Windows PowerShell 5.1 | `NativeCommandError` へ昇格 | 止まる |
| PowerShell 7 | 昇格しない | **止まらない** |

差は昇格の有無だけである．非 0 終了そのものは，どちらの版でも止めない．

この誤解が具体的な穴になっていた．`git ls-remote` である．

```powershell
$RemoteMajorLine = git ls-remote origin "refs/tags/${Major}"
$RemoteMajorSha = if ($RemoteMajorLine) { ... } else { '' }
```

出力なしには「タグが無い」と「照会が失敗した」の 2 つが混ざる．
認証切れで失敗すると，7 では黙って lease 無し push の経路へ落ちる．
`--force-with-lease` の保護が外れた状態で major mutable を動かすことになる．

**bash 版にも同じ穴があった．**

```bash
REMOTE_MAJOR_SHA="$(git ls-remote origin "refs/tags/${MAJOR}" | cut -f1)"
```

パイプの終了コードは `cut` のものである．`git` の失敗は `set -e` に届かない．
`bin/watch-pr-checks.sh` の `refs/heads/` 照会も同型であった．

両版の 4 箇所で終了コードを明示的に検査する形へ改めた．

`--exit-code` は使わなかった．本スクリプトは「対象が無い」を正常な分岐として扱う．
`release-patch` ではタグ未作成の初回，`watch-pr-checks` では push 忘れが当たる．
`--exit-code` を付けると，この 2 つが再び失敗と同じ終了コードへ潰れる．

**知見**: `Stop` を置いたから失敗したら止まる，という理解は誤りである．
出力の有無で分岐する呼び出しは，終了コードも必ず見る．
沈黙する失敗は，5.1 と 7 で振る舞いが分かれる形で現れる．

## 📏 テスト設計で判断したこと

移植の食い違いを 1 件検出した．
本実行時の `git cat-file` が，bash 版では dry-run 限定なのに対し
PowerShell 版では無条件に走っていた．
読み取り専用のため実害は無いが，同じ実行列を持つ約束から外れる．
実行列を 1 行ずつ突き合わせるテストがこれを拾った．

bats に在って Pester へ持ち込まなかったケースが 2 つある．
引数不足とオプション値の欠落である．
PowerShell の parameter binder が拒むため，対象スクリプトの責務ではない．
必須パラメーターの未指定は子プロセスで入力待ちになりうる点も避けた．

スタブの引数受け取りでは 2 度つまずいた．

- `param([Parameter(ValueFromRemainingArguments)]...)` を置くと，
  `-e` や `-q` が共通パラメーター（`-ErrorAction` 等）の前方一致で吸われる．
  自動変数 `$args` で受ければ素通しできる．
- 対象スクリプトは `& 'git' @(...)` の形で呼ぶ．
  native command なら配列は個々の引数へ展開されるが，
  関数へは配列 1 個として渡る．スタブ側で 1 段だけ平坦化して合わせた．

**知見**: 対処を消してテストが落ちるかを必ず確かめる．
ヘルパーの緩和を外すと 5.1 系の 3 ケースが落ちることを実測した．
落ちなければ，そのテストは何も守っていない．

## 🧭 残した宿題

- **CI で 5.1 を検査していない．** ubuntu runner のため 2 ケースが skip される．
  windows runner を `shell-quality` へ足すかは別途判断する（Issue #184）．
- **規律を機械で守れていない．** 直接呼びを書いた `.ps1` を gate が通す（Issue #185）．
- **直接呼びを残した箇所がある．** `git fetch` と
  `git rev-parse --is-shallow-repository` である．
  7 で素通りしても直後の祖先検査が非 0 で終えるため沈黙しない．
  ただし出るエラー文は実際の原因と食い違う．

前 2 件は起票した．手元のメモに留めると，別セッションの自分へ届かない．
`v2.16.1` と `v2.17.2` で 2 度踏んだのは，まさにそれが理由であった．

## 📎 参照

- Issue #179・#167．PR #182．リリースは `v2.18.0`．
- 規律は [docs/shell-quality.md](../shell-quality.md) の
  `native command の呼び出し規律` 節にある．
- 発端の記録は [2026-09-04-issue174-prh-object-object.md](2026-09-04-issue174-prh-object-object.md)．
- 受け皿の整備は [2026-09-03-issue133-watch-pr-checks.md](2026-09-03-issue133-watch-pr-checks.md)．
