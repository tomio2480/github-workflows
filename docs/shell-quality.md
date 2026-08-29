# Shell / CLI quality reusable workflow

## 要約

各 repo が所有する `verify-shell` command を同じ toolchain で実行する．
中央 workflow は共通 toolchain を配置する．
対象は ShellCheck，shfmt，Bats，PSScriptAnalyzer，Pester である．
検証ロジックは caller repo へ残す．

## 責務

中央 workflow の責務は次の 2 点である．

- version を固定した検証 toolchain の配置
- caller repo の `verify-shell` script を `--require-all` 付きで実行

lint 対象，除外，test suite，CLI contract は caller repo が決める．
中央 repo へ repo 固有の path や検証規則を追加しない．

## 導入

`templates/.github/workflows/shell-quality.yml` を caller repo へコピーする．
`OWNER` と `<SHA>` は利用する中央 repo と確定 commit SHA に置換する．

caller repo は `bin/verify-shell.py` を用意し，次の契約を満たす必要がある．

```text
python bin/verify-shell.py --require-all
```

- 成功は exit code 0，失敗は非 0 を返す．
- `--require-all` では tool 不足も失敗にする．
- subprocess は argv 配列で起動し，input を command string として評価しない．
- JSON や複数行 payload は stdin または file で渡す．

script の path が異なる場合は caller の `verify-script` input を変更する．
この input は shell 変数へ渡して引用するため，空白を含む path も 1 引数になる．

## Tool version

| Tool | Version | 固定方法 |
|---|---:|---|
| ShellCheck | 0.11.0 | release asset と SHA-256 |
| shfmt | 3.13.1 | release asset と SHA-256 |
| Bats | 1.14.0 | commit archive と SHA-256 |
| PSScriptAnalyzer | 1.25.0 | PowerShell Gallery の required version |
| Pester | 6.1.0 | PowerShell Gallery の required version |

workflow の変更は self-test workflow から local reusable workflow を呼ぶ．
self-test は `.github/workflows/test-self-lint.yml` に置く．
fixture gate が全 tool と module を検出できることで確認する．
