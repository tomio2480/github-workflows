# 🐚 Shell / CLI quality reusable workflow

## 🎯 要約

各 repo が所有する `verify-shell` command を同じ toolchain で実行する．
中央 workflow は共通 toolchain を配置する．
対象は ShellCheck，shfmt，Bats，PSScriptAnalyzer，Pester である．
検証ロジックは caller repo へ残す．

## 🗺 目次

- 🧭 責務
- 🚀 導入
- 📌 Tool version
- 🔄 更新手順
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

## 🧪 自己テスト

workflow の変更は self-test workflow から local reusable workflow を呼ぶ．
self-test は `.github/workflows/test-self-lint.yml` に置く．
fixture gate は CLI tool と PowerShell module の version を固定値と突合する．
pytest は `--require-all` が無い呼び出しを拒否することも確認する．
`--require-all` で tool が不足した場合の非ゼロ終了も確認する．
