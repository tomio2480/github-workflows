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
    cat "${ACTION_PATH}/package.json" "${ACTION_PATH}/package-lock.json" |
      sha256sum | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then
    cat "${ACTION_PATH}/package.json" "${ACTION_PATH}/package-lock.json" |
      shasum -a 256 | cut -d' ' -f1
  else
    echo "neither sha256sum nor shasum is available" >&2
    return 1
  fi
}

emit_outputs() {
  echo "bin=$1/node_modules/.bin" >>"${GITHUB_OUTPUT}"
  echo "modules=$1/node_modules" >>"${GITHUB_OUTPUT}"
}

CACHE_KEY_DIR=""
if [ -n "${CACHE_DIR}" ]; then
  CACHE_KEY_DIR="${CACHE_DIR}/$(hash_manifest)"
  if [ -d "${CACHE_KEY_DIR}/node_modules/.bin" ]; then
    emit_outputs "${CACHE_KEY_DIR}"
    echo "Reusing cache: ${CACHE_KEY_DIR}"
    exit 0
  fi
  # 鍵の位置へ直接組み立てない．同時に走った別プロセスが未完成の状態を掴み，
  # こちらが失敗すると後始末が相手の使用中ディレクトリを消してしまう．
  # 組み立ては専用ディレクトリで行い，完成後に鍵の位置へ移す．
  mkdir -p "${CACHE_DIR}"
  TMP="$(mktemp -d "${CACHE_DIR}/.staging.XXXXXX")"
else
  TMP="$(mktemp -d "${RUNNER_TEMP}/XXXXXX")"
fi

# 失敗時に消すのは自前の組み立て先だけである．公開済みのキャッシュには触れない．
trap 'rm -rf "${TMP}"' ERR
cp "${ACTION_PATH}/package.json" "${TMP}/"
cp "${ACTION_PATH}/package-lock.json" "${TMP}/"
(cd "${TMP}" && npm ci)

if [ -n "${CACHE_KEY_DIR}" ]; then
  # 公開は 1 度の rename で行う．競合に負けた場合は相手の成果を使い，
  # 自分の組み立て先を捨てる．どちらの経路でも未完成の状態は見えない．
  if [ -e "${CACHE_KEY_DIR}" ] || ! mv "${TMP}" "${CACHE_KEY_DIR}" 2>/dev/null; then
    rm -rf "${TMP}"
  fi
  if [ ! -d "${CACHE_KEY_DIR}/node_modules/.bin" ]; then
    echo "cache key path is not usable: ${CACHE_KEY_DIR}" >&2
    exit 1
  fi
  TMP="${CACHE_KEY_DIR}"
fi

emit_outputs "${TMP}"
echo "Installed under: ${TMP}"
