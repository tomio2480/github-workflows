#!/usr/bin/env bash
# package.json と package-lock.json を ACTION_PATH から tmpdir にコピーし
# npm ci で lint 依存パッケージ（markdownlint-cli2・textlint 一式）を
# インストールする．composite action の Install lint dependencies step から呼ばれる．
#
# 入力（環境変数）:
#   ACTION_PATH   - package.json / package-lock.json が置かれた action ディレクトリ（必須）
#   RUNNER_TEMP   - tmpdir 作成先のベースディレクトリ（必須）
#   GITHUB_OUTPUT - GitHub Actions output ファイルのパス（必須）
#   LINT_DEPS_CACHE_DIR - 再利用キャッシュの置き場所（任意．Issue #134）
#
# LINT_DEPS_CACHE_DIR を空でない値にすると，インストール先を
# <cache_dir>/<package.json と package-lock.json の内容ハッシュ> へ固定し，
# node_modules/.bin が既にあれば npm ci を省略して再利用する．
# push 前ローカル lint（bin/lint-md.sh）が毎回の npm ci を避けるために使う．
# CI は本変数を渡さないため，runner 上の挙動は従来どおり 1 回限りの tmpdir となる．
# 依存が変われば鍵も変わるため，古い node_modules を掴むことはない．
#
# 出力（GITHUB_OUTPUT）:
#   bin=<dir>/node_modules/.bin
#   modules=<dir>/node_modules
#
# stdout:
#   "Installed under: <dir>"（インストールを実行した場合）
#   "Reusing cache: <dir>"（キャッシュを再利用した場合）

set -euo pipefail

: "${ACTION_PATH:?ACTION_PATH is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

CACHE_DIR="${LINT_DEPS_CACHE_DIR:-}"

# 依存の同一性は manifest と lockfile の内容だけで決まる．sha256 の実装名は
# 環境で割れる（GNU は sha256sum，macOS は shasum）ため両方を見る．
hash_manifest() {
  if command -v sha256sum >/dev/null 2>&1; then
    cat "${ACTION_PATH}/package.json" "${ACTION_PATH}/package-lock.json" \
      | sha256sum | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    cat "${ACTION_PATH}/package.json" "${ACTION_PATH}/package-lock.json" \
      | shasum -a 256 | cut -d' ' -f1
  else
    echo "neither sha256sum nor shasum is available" >&2
    return 1
  fi
}

emit_outputs() {
  echo "bin=$1/node_modules/.bin" >>"${GITHUB_OUTPUT}"
  echo "modules=$1/node_modules" >>"${GITHUB_OUTPUT}"
}

if [ -n "${CACHE_DIR}" ]; then
  TMP="${CACHE_DIR}/$(hash_manifest)"
  if [ -d "${TMP}/node_modules/.bin" ]; then
    emit_outputs "${TMP}"
    echo "Reusing cache: ${TMP}"
    exit 0
  fi
  mkdir -p "${TMP}"
else
  TMP="$(mktemp -d "${RUNNER_TEMP}/XXXXXX")"
fi

# 失敗時は中途半端な状態を残さない．キャッシュ側も鍵つきの自前ディレクトリの
# ため，消しておけば次回の再実行がやり直しになる．
trap 'rm -rf "${TMP}"' ERR
cp "${ACTION_PATH}/package.json" "${TMP}/"
cp "${ACTION_PATH}/package-lock.json" "${TMP}/"
(cd "${TMP}" && npm ci)
emit_outputs "${TMP}"
echo "Installed under: ${TMP}"
