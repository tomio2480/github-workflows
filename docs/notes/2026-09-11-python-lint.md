# Python 品質 gate と中央 CI の分担

## 状態

採用．2026-09-11．ローカル実装と検証の記録であり，GitHub での公開・CI 成功を示すものではない．
要求は [settings #261](https://github.com/tomio2480/settings/issues/261) にある．

## 背景

Python ガイドに書いた Ruff・mypy を実行する中央 CI が無かった．
一方，本 repo は caller 固有の規則を中央へ移さず，環境準備と呼び出しを受け持つ．
検査の欠落を成功とせず，通常出力を小さくして全文を後から読めることも必要だった．

## 判断

Shell quality と同様に reusable workflow と caller 所有 gate の雛形を配る．
最初は実行例と同じ uv project を対象にし，Python・uv と caller の lock を使って環境を揃える．
Ruff と mypy の版を中央と caller の別々の依存一覧へ二重管理しない．

Ruff の lint と整形は必須とし，同じ探索済みファイルへ実行する．
探索には既存 parser を持つ Ruff を使い，除外構文を独自に再実装しない．
formatter の個別除外で対象が欠けないよう，明示したファイルには除外を再適用しない．
lint が失敗しても整形確認・型検査へ進み，各結果を記録する．

mypy は project の設定を opt-in の根拠とする．
独立した opt-in job ではなく同じ job の検査状態に分け，同一の依存環境と記録を使う．
対象外と未実行は分ける．型検査の対象範囲は mypy 設定が所有する．

実行の記録は一意のディレクトリにまとめる．元ログを読み切ってから要約する必要をなくす．
中央の権限は contents の読み取りだけとし，checkout の credentials を残さない．
caller の入力を shell の command string に展開せず，環境変数から引用して渡す．

## 代替案

- 中央で毎回最新の Ruff・mypy を install: caller のローカル環境とずれるため採らない．
- 全 repo に型検査を強制: 未注釈の既存コードへの段階導入を妨げるため採らない．
- reusable workflow から中央の script を相対参照: checkout 対象は caller なので採らない．
- すべての依存管理方式に対応: 認証・extras・lock 等の差が増えるため，実利用の要件が出てから拡張する．
- 長い説明を workflow のコメントに追加: 契約は専用文書，判断は本記録へ置く．

## 検証

gate の契約テストを先に作り，未実装で 19 件の失敗と CLI 解析 1 件の成功を確認した．
実装後は 20 件が成功した．空白・日本語・引用符を持つ cwd と，全文ログの保存も実 process で確認した．
Ruff の無い隔離環境と 151 ファイルの引数分割を追加し，workflow 契約を含む関連 24 件も成功した．
実 Ruff／mypy による 9 つの対照は Windows / Python 3.13 で成功した．
lint・整形・型違反，mypy 対象外，対象 0 件，全除外，formatter 個別除外，mypy の欠落 path を含む．
中央の local caller と対照テストを Linux self-test に追加した．GitHub 上での実行は未実施である．
YAML の Bash step 自体を Git Bash で実行し，lock 同期・Ruff・strict mypy・対照テストを確認した．
既存を含む Python 全体 434 件，Shell gate，Pester 75 件，actionlint も成功した．
static security は argv・書込先・権限・依存の出所をレビューした．脆弱性監査の実行は含めていない．

## 影響と見直し条件

uv.lock を持たない repo は本版の workflow をそのまま使えない．
gate の配布コピーは caller の管理対象となり，中央の SHA 更新だけでは更新されない．
新しい依存管理方式・notebook・異なる Ruff 設定の混在が必要になれば，独立した要件と対照を先に追加する．
この gate の成功で，security の全観点や TDD の順序を機械的に保証しない．

## 根拠

- [GitHub の reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)．
- [uv と GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/)．
- [uv の lock と同期](https://docs.astral.sh/uv/concepts/projects/sync/)．
- [uv と Dependabot](https://docs.astral.sh/uv/guides/integration/dependabot/)．
- [Ruff の設定とファイル探索](https://docs.astral.sh/ruff/configuration/)．
- [mypy の設定探索と対象](https://mypy.readthedocs.io/en/stable/config_file.html)．
