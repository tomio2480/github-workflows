#!/usr/bin/env bash
# package.json と package-lock.json を ACTION_PATH から tmpdir にコピーし
# npm ci で textlint 依存パッケージをインストールする．
# composite action の Install textlint step から呼ばれる．
#
# 入力（環境変数）:
#   ACTION_PATH   - package.json / package-lock.json が置かれた action ディレクトリ（必須）
#   RUNNER_TEMP   - tmpdir 作成先のベースディレクトリ（必須）
#   GITHUB_OUTPUT - GitHub Actions output ファイルのパス（必須）
#
# 出力（GITHUB_OUTPUT）:
#   bin=<tmpdir>/node_modules/.bin
#   modules=<tmpdir>/node_modules
#
# stdout:
#   "Installed under: <tmpdir>"

set -euo pipefail

: "${ACTION_PATH:?ACTION_PATH is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

TMP="$(mktemp -d "${RUNNER_TEMP}/XXXXXX")"
trap 'rm -rf "${TMP}"' ERR
cp "${ACTION_PATH}/package.json" "${TMP}/"
cp "${ACTION_PATH}/package-lock.json" "${TMP}/"
(cd "${TMP}" && npm ci)
echo "bin=${TMP}/node_modules/.bin" >> "${GITHUB_OUTPUT}"
echo "modules=${TMP}/node_modules" >> "${GITHUB_OUTPUT}"
echo "Installed under: ${TMP}"
