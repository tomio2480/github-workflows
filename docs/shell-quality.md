# 🐚 Shell / CLI quality reusable workflow

## 🎯 要約

各 repo が所有する `verify-shell` command を同じ toolchain で実行する．
中央 workflow は共通 toolchain を配置する．
対象は ShellCheck，shfmt，Bats，PSScriptAnalyzer，Pester である．
検証ロジックは caller repo へ残す．
本リポジトリ自身の gate は `bin/verify-shell.py` に置く．

## 🗺 目次

- 🧭 責務
- 🚀 導入
- 🪟 任意の windows job
- 📌 Tool version
- 🔄 更新手順
- 🏠 中央リポジトリ自身の gate
- 🧩 native command の呼び出し規律
- 🧪 自己テスト

## 🧭 責務

中央 workflow の責務は次の 2 点である．

- version を固定した検証 toolchain の配置
- caller repo の `verify-shell` script を `--require-all` 付きで実行

lint 対象，除外，test suite，CLI contract は caller repo が決める．
中央 repo へ repo 固有の path や検証規則を追加しない．

## 🚀 導入

`templates/.github/workflows/shell-quality.yml` を caller repo へコピーする．
`OWNER` は利用する中央 repo の owner に置換する．
`<SHA>` は確定 commit SHA に置換する．

caller repo は `bin/verify-shell.py` を用意し，次の契約を満たす必要がある．

```text
python bin/verify-shell.py --require-all
```

- 成功は exit code 0，失敗は非 0 を返す．
- `--require-all` では tool 不足も失敗にする．
- subprocess は argv 配列で起動し，input を command string として評価しない．
- JSON や複数行 payload は stdin または file で渡す．

script の path が異なる場合は caller の `verify-script` input を変更する．
caller workflow の `pull_request.paths` も同じ path へ変更する．
この input は shell 変数へ渡して引用するため，空白を含む path も 1 引数になる．

## 🪟 任意の windows job

`windows-verify: true` を渡すと，windows runner の job が並ぶ．
既定は `false` であり，渡さない caller の挙動は変わらない．

有効にした caller の verify script は，次の呼び出しも解する必要がある．

```text
python bin/verify-shell.py --require-all --powershell-only
```

- PSScriptAnalyzer と Pester だけを実行する．
- ShellCheck と shfmt の不足を失敗にしない．windows へは載せないためである．
- Pester の対象が 0 件なら失敗する．
- skip されたテストが 1 件でもあれば失敗する．

後ろの 2 つは，この job が緑のまま何も検査しない状態を止めるためにある．
5.1 を要するテストは，5.1 が無ければ自ら skip する．
それを許すと，5.1 のために設けた job が skip の山を緑で返す．
本リポジトリでは `bin/run-pester.ps1 -FailOnSkipped` がこれを担う．

この 2 つを ubuntu の job へは広げない．
そちらは PowerShell 資産を持たない caller も通る汎用の gate である．
対象 0 件も 5.1 不在の skip も，そこでは正常な状態に当たる．
`windows-verify` を有効にすること自体が
「5.1 を要するテストを持つ」という宣言であり，非対称はそこに根拠がある．

skip を一律で失敗にする点は，いまは skip の理由が 5.1 の不在に限られるためである．
windows 上で正当に skip したいテストが出たら，この判定を見直す．

有効にする理由は Windows PowerShell 5.1 にある．
5.1 は ubuntu runner に無い．
`powershell.exe` の有無で skip するテストは，そこで飛ぶ．
昇格の癖（後述「native command の呼び出し規律」）は 5.1 でのみ起きるため，
関数スタブでは代替できない．
本リポジトリでは 5.1 依存の 2 ケースが ubuntu で skip されていた（Issue #184）．

bash 側の検査は ubuntu の job が担う．
ShellCheck と shfmt を Windows へ導入せず，CRLF の差異も持ち込まない．

## 📌 Tool version

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 1: Shell quality toolchain の固定版

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| Tool | Version | 固定方法 |
|---|---:|---|
| ShellCheck | 0.11.0 | release asset と SHA-256 |
| shfmt | 3.13.1 | release asset と SHA-256 |
| Bats | 1.14.0 | tag が指す commit SHA を shallow fetch |
| PSScriptAnalyzer | 1.25.0 | PowerShell Gallery の required version |
| Pester | 6.1.0 | PowerShell Gallery の required version |

## 🔄 更新手順

上表の tool version は Dependabot の監視対象外である．
更新は maintainer が次の手順で行う．

1. 公式 release または PowerShell Gallery で新しい版を確認する．
2. workflow の URL，version，commit SHA を更新する．
3. release asset は取得物の SHA-256 を実測して更新する．
4. Bats は tag が指す commit SHA と行内の版コメントを同時に更新する．
5. fixture の期待 version と本書の表を同じ commit で更新する．
6. Draft PR で self-test と caller contract が成功することを確認する．

定期的な更新検知の自動化は Phase 2 候補とする．
更新 PR を自動生成するまでは，release 時の手動確認を必須とする．

## 🏠 中央リポジトリ自身の gate

本リポジトリもシェル資産を持つ caller である．
repo-local gate は `bin/verify-shell.py` に置く．
`test-self-lint.yml` の `shell-quality-self` job から呼ぶ．

<!-- textlint-disable ja-technical-writing/ja-no-mixed-period -->

表 2: repo-local gate の検査対象と実行ツール

<!-- textlint-enable ja-technical-writing/ja-no-mixed-period -->

| 検査対象 | 実行するツール |
|---|---|
| `bin/*.sh`・`scripts/*.sh` | ShellCheck，shfmt（`-d -i 2 -ci`） |
| `bin/*.ps1`・`bin/lib/*.ps1` | PSScriptAnalyzer（Error と Warning） |
| `tests/powershell/*.Tests.ps1` | Pester（`bin/run-pester.ps1` 経由） |

Bats は `unit-bash` job が同じ suite を実行するため gate へ含めない．
Pester は bats を持たない PowerShell 版の振る舞いを担保するため gate で実行する．
対象が 1 つも無ければ実行しない．

`tests/powershell/fixtures/` は，どちらの glob にも入らない．
`bin/run-pester.ps1` の回帰確認に使う資材を置く場所である．
構文の壊れた `.ps1` を意図して含むため，検査対象から外す．
glob を再帰へ変えると，この fixture が本体の suite に混ざる．

本リポジトリは `windows-verify: true` を渡す．
5.1 依存のテストを持つためである（前節参照）．
ubuntu と windows の 2 job が並び，PowerShell の検査は両方で走る．

fixture 呼び出し（`shell-quality-reusable` job）とは統合しない．
前者は toolchain と caller contract を検証する自己テストである．
後者は配布物ではない実資産を検査する gate であり，役割が異なる．

shfmt の整形規則は `-i 2 -ci` とする．
既存スクリプトのインデント幅と case 分岐の字下げに合わせた選択である．

`.ps1` は UTF-8 BOM 付きで保存する．
非 ASCII を含むファイルへの `PSUseBOMForUnicodeEncodedFile` を満たす．
Windows PowerShell 5.1 で読ませたときの文字化けも同時に防げる．

シェル資産は `.gitattributes` により LF で checkout する．
CRLF の worktree では ShellCheck が SC1017 を全行へ出すためである．
これがないと Windows 上でローカル実行が成立しない．
テスト用の `.cmd` スタブだけは CRLF とする．`cmd` の解析が行末に敏感なためである．

## 🧩 native command の呼び出し規律

終了コードで分岐する native command は `Invoke-NativeCommand` 経由で呼ぶ．
実体は `bin/lib/native.ps1` にあり，各スクリプトから dot-source して使う．

Windows PowerShell 5.1 には昇格の癖がある．
`$ErrorActionPreference = 'Stop'` のもとで，
native command の stderr を終了エラーへ変える．
昇格はリダイレクトより先に起きるため，呼び出し側では抑止できない．
`gh release view` のように「stderr を出しつつ非 0 で終える」正常な分岐が，
これで潰れる（Issue #179）．

出力の有無で分岐する呼び出しは，終了コードも必ず検査する．
`git ls-remote` が当たる．
出力なしには「対象が無い」と「照会が失敗した」の 2 つが混ざる．
区別しないと，認証切れが別の失敗へ化ける．

直接呼びのまま残せるのは，失敗が次の手順で必ず表面化する呼び出しに限る．
`git fetch` と `git rev-parse --is-shallow-repository` が当たる．
5.1 は昇格でその場が止まる．
7 は素通りするが，直後の祖先検査が非 0 で終える．

「`$ErrorActionPreference = 'Stop'` があるから fail-fast する」とは考えない．
7 は native command の非 0 終了で停止しない．
5.1 だけが stderr で止まる．両者の差は昇格の有無だけである．

## 🧪 自己テスト

workflow の変更は self-test workflow から local reusable workflow を呼ぶ．
self-test は `.github/workflows/test-self-lint.yml` に置く．
fixture gate は CLI tool と PowerShell module の version を固定値と突合する．
pytest は `--require-all` が無い呼び出しを拒否することも確認する．
`--require-all` で tool が不足した場合の非ゼロ終了も確認する．
