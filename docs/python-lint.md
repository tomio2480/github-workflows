# Python lint reusable workflow

## 要約

uv project の Ruff lint・整形確認・任意の mypy を，caller 所有の gate で実行する．
検査失敗は job を失敗させる．中央は環境準備と呼び出し，対象と規則は caller が所有する．

## 目次

- 導入
- 検査の契約
- 出力
- 更新と自己検証
- 保証の範囲

## 導入

次の雛形を caller にコピーする．既存ファイルがある場合は差分を統合する．

- [caller workflow](../templates/.github/workflows/python-lint.yml) を `.github/workflows/python-lint.yml` へ置く．
- [gate](../templates/verify-python.py) を project 内の `bin/verify-python.py` へ置く．

workflow の `OWNER` と `<SHA>` は，利用できる中央 repo の owner と full commit SHA に置換する．
未公開のローカル commit は GitHub Actions から参照できない．
caller の Dependabot には `github-actions` ecosystem の `directory: /` を設定する．
既存の updates へ統合し，設定全体を上書きしない．

最初の対象は Python 3.11 以降の uv project とする．既存の pip や Poetry を自動移行しない．
project の `pyproject.toml` と `uv.lock` を追跡し，`dev` dependency group に Ruff を宣言する．
mypy を有効にする場合は mypy と必要な stubs・plugin も同じ group に含める．
CI は project の runtime 依存と `dev` group を `--locked` で同期する．
追加の group・extras が必須の構成は，この workflow の対応範囲を先に見直す．

`[tool.ruff]` と次の対象宣言を pyproject に置く．`src`・`tests` は実際の構成に合わせる．

```toml
[tool.python-quality]
targets = ["src", "tests"]
```

path は project 内の既存ファイルかディレクトリを指定する．glob は使わない．
規則と lock の実例は [fixture](../tests/fixtures/python-quality/pyproject.toml) にある．
この fixture の設定を既存 project 全体へ上書きしない．

表 1: workflow の入力．

| 入力 | 既定値 | 用途 |
|---|---|---|
| working-directory | `.` | pyproject と lock を持つ caller 内のディレクトリ |
| verify-script | `bin/verify-python.py` | working-directory からの gate の相対 path |
| python-version | `3.13` | 実行する Python．caller の対応版と一致させる |
| uv-version | `0.11.2` | uv の固定版 |
| artifact-name | `python-lint` | 同じ workflow run 内では呼び出しごとに異なる名前にする |

Python を matrix で複数回実行する場合は，artifact-name も版ごとに変える．
gate をローカルで実行するときも，project のディレクトリを起点にする．

```text
uv run --locked --python 3.13 --no-default-groups --group dev python bin/verify-python.py
```

## 検査の契約

各宣言 path に `ruff check --show-files` を使い，Ruff 自身の設定に従って対象を決める．
1 つでも対象の Python ファイルが 0 件なら失敗する．gate 自身だけでは対象ありと数えない．
確定した `.py`・`.pyi` を lint と整形の両方へ同じ順で渡す．大量の場合は分割する．
`--no-force-exclude` を付け，formatter 固有の除外でもこの集合が欠落しないようにする．
対象の除外は共通の Ruff discovery 側で決める．一部のファイルは lint だけに掛ける構成には対応しない．

Ruff は `--config pyproject.toml` で設定を固定する．HOME や子ディレクトリの別設定へ切り替えない．
lint は `--no-fix --no-unsafe-fixes`，整形は `--check` を指定し，検査時にソースを修正しない．
一方の指摘があっても，他方と有効な mypy を実行して結果を残す．

mypy は project 直下の `mypy.ini`，`.mypy.ini`，`[tool.mypy]`，`setup.cfg` の `[mypy]` の順に選ぶ．
選んだファイルを `--config-file` で明示する．HOME や親 project の設定は opt-in に数えない．
設定には `files`・`modules`・`packages` のいずれかで段階導入の対象を宣言する．
設定が無ければ理由付き `not_applicable`，有れば必須検査となる．
壊れた設定，対象指定の欠落，tool 不足，実行失敗を対象外へ読み替えない．
mypy は設定の誤りを stderr へ出すだけで，失敗にしない場合がある．
設定ファイル名で始まる診断が出た場合は，行番号の有無や終了コードによらず設定のエラーとする．

## 出力

通常出力は各検査の状態と `report.json` の場所だけを示す．
既定は OS の一時領域，`--report-dir PATH` 指定時はその下に一意の実行ディレクトリを作る．
JSON は対象一覧，設定・lock の hash，Python と tool の版，各 argv と終了コードを記録する．
各 process の stdout と stderr は別ファイルに全文を残す．JSON 内のログ名は同じディレクトリからの相対 path である．

表 2: 終了と状態．

| 終了コード | 意味 |
|---|---|
| 0 | 必須の検査が成功．mypy の対象外は明示 |
| 1 | 実行した lint・整形・型検査の失敗 |
| 2 | 設定・対象探索・起動等のエラー，または CLI の使い方の誤り |

`planned` は未実行であり，成功ではない．
CLI の引数誤りや記録先の作成失敗では，JSON を残せないことがある．
CI は gate 失敗時も artifact の保存を試み，保存期間を 7 日とする．
依存の同期より前に失敗した場合は gate の記録が無いため，Actions の step log を読む．
機密情報を診断や plugin のログへ出す project では，導入前に保存対象とアクセス権を確認する．

## 更新と自己検証

中央の third-party actions は full SHA で固定し，既存の Dependabot が更新する．
fixture の開発依存は Dependabot の uv ecosystem が uv.lock を更新する．
caller 側も pyproject の配置先に合わせて依存更新を設定する．
コピーした gate は caller 所有となるため，workflow の SHA 更新だけでは書き換わらない．
変更時は template の差分と caller の対象・回帰テストを照合する．

中央は local reusable caller と実 Ruff／mypy の正常・違反・除外の対照を self-test に持つ．
process 境界，未実行と対象外，大量出力は [契約テスト](../tests/python/test_templates_verify_python.py) が扱う．
更新の採否と実測した環境は [ADR](notes/2026-09-11-python-lint.md) に記録する．

## 保証の範囲

この gate は pytest，依存の脆弱性監査，packaging，TDD の作業順を検査しない．
各 repo の既存の必須 test と security gate は維持する．
宣言した範囲の実行を確認するが，規則の十分さや未宣言の必要ファイルを自動で判断するものではない．
notebook，子 project ごとの異なる Ruff 設定，private dependency の認証は本版の対象外である．
