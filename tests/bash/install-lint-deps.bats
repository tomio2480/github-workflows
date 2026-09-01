#!/usr/bin/env bats

# scripts/install-lint-deps.sh unit tests.
#
# Spec:
#   Input (environment variables):
#     ACTION_PATH   - absolute path to the action dir (holds package.json / package-lock.json) [required]
#     RUNNER_TEMP   - base dir for tmpdir creation [required]
#     GITHUB_OUTPUT - GitHub Actions output file path [required]
#     LINT_DEPS_CACHE_DIR - reusable cache root for local runs [optional]
#   Behavior:
#     - Creates a tmpdir under RUNNER_TEMP
#     - Copies package.json / package-lock.json from ACTION_PATH to the tmpdir
#     - Runs "npm ci" inside the tmpdir
#     - Writes "bin=<tmpdir>/node_modules/.bin" to GITHUB_OUTPUT
#     - Writes "modules=<tmpdir>/node_modules" to GITHUB_OUTPUT
#     - Prints "Installed under: <tmpdir>" to stdout
#     - Exits non-zero if npm ci fails
#     - Exits non-zero if any required env var is missing
#
# Test strategy:
#   Inject a fake npm into PATH so no real network install is performed.
#   fake npm creates node_modules/.bin on "npm ci" and exits ${NPM_CI_EXIT:-0}.

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/install-lint-deps.sh"
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  ACTION_STUB="${BATS_TEST_TMPDIR}/action"
  mkdir -p "${FAKE_BIN}" "${ACTION_STUB}"

  export NPM_CWD_LOG="${BATS_TEST_TMPDIR}/npm-cwd"
  cat > "${FAKE_BIN}/npm" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  ci)
    pwd > "${NPM_CWD_LOG}"
    mkdir -p "./node_modules/.bin"
    # 競合相手が先に公開を終える状況を作るためのフック．
    if [ -n "${RIVAL_PUBLISH_DIR:-}" ]; then
      mkdir -p "${RIVAL_PUBLISH_DIR}/node_modules/.bin"
    fi
    exit "${NPM_CI_EXIT:-0}"
    ;;
  *)
    exit 0
    ;;
esac
FAKE
  chmod +x "${FAKE_BIN}/npm"
  PATH="${FAKE_BIN}:${PATH}"
  export PATH

  echo '{"name":"stub","dependencies":{}}' > "${ACTION_STUB}/package.json"
  echo '{"lockfileVersion":3,"packages":{}}' > "${ACTION_STUB}/package-lock.json"

  export GITHUB_OUTPUT="${BATS_TEST_TMPDIR}/github_output"
  touch "${GITHUB_OUTPUT}"

  export ACTION_PATH="${ACTION_STUB}"
  export RUNNER_TEMP="${BATS_TEST_TMPDIR}"
}

# スクリプトと同じ規則で鍵を組み立てる．テストから公開先を先回りして作る．
cache_key() {
  cat "${ACTION_STUB}/package.json" "${ACTION_STUB}/package-lock.json" |
    sha256sum | cut -d' ' -f1
}

teardown() {
  unset ACTION_PATH RUNNER_TEMP GITHUB_OUTPUT NPM_CI_EXIT LINT_DEPS_CACHE_DIR \
    NPM_CWD_LOG RIVAL_PUBLISH_DIR
}

@test "exits 0 and writes bin and modules to GITHUB_OUTPUT on success" {
  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q "^bin=.*node_modules/\.bin$" "${GITHUB_OUTPUT}"
  grep -q "^modules=.*node_modules$" "${GITHUB_OUTPUT}"
}

@test "prints 'Installed under:' to stdout" {
  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"Installed under:"* ]]
}

@test "copies package.json and package-lock.json into the tmpdir" {
  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  INSTALLED_DIR="${output##*Installed under: }"
  [ -f "${INSTALLED_DIR}/package.json" ]
  [ -f "${INSTALLED_DIR}/package-lock.json" ]
}

@test "exits non-zero when npm ci fails" {
  export NPM_CI_EXIT=1

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "exits non-zero when ACTION_PATH is unset" {
  unset ACTION_PATH

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "exits non-zero when RUNNER_TEMP is unset" {
  unset RUNNER_TEMP

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "exits non-zero when GITHUB_OUTPUT is unset" {
  unset GITHUB_OUTPUT

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

# --- LINT_DEPS_CACHE_DIR: push 前ローカル lint 向けの再利用キャッシュ（Issue #134）---
#
# Spec:
#   LINT_DEPS_CACHE_DIR が空でないとき，インストール先を
#   "${LINT_DEPS_CACHE_DIR}/<package-lock.json の内容ハッシュ>" に固定する．
#   同ディレクトリに node_modules/.bin が既にあれば npm ci を省略して再利用し，
#   "Reusing cache: <dir>" を stdout に出す．
#   無ければ従来どおり copy + npm ci し，"Installed under: <dir>" を出す．
#   lockfile が変われば別ディレクトリになり，古い依存を掴まない．
#   未設定・空文字のときの挙動は従来の RUNNER_TEMP 配下 mktemp -d から変わらない．

@test "installs into a lockfile-keyed dir under LINT_DEPS_CACHE_DIR" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  INSTALLED_DIR="${output##*Installed under: }"
  [[ "${INSTALLED_DIR}" == "${LINT_DEPS_CACHE_DIR}/"* ]]
  [ -f "${INSTALLED_DIR}/package-lock.json" ]
}

@test "reuses the cached dir and skips npm ci on the second run" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  run bash "${SCRIPT}"
  [ "${status}" -eq 0 ]

  # 2 回目で npm が呼ばれたら分かるように，必ず失敗する fake へ差し替える．
  cat > "${FAKE_BIN}/npm" <<'FAKE'
#!/usr/bin/env bash
echo "npm must not be called on cache hit" >&2
exit 9
FAKE
  chmod +x "${FAKE_BIN}/npm"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"Reusing cache:"* ]]
  grep -q "^bin=${LINT_DEPS_CACHE_DIR}/.*node_modules/[.]bin$" "${GITHUB_OUTPUT}"
}

@test "uses a different cache dir when the lockfile changes" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  run bash "${SCRIPT}"
  [ "${status}" -eq 0 ]
  FIRST_DIR="${output##*Installed under: }"

  echo '{"lockfileVersion":3,"packages":{"":{"name":"changed"}}}' \
    > "${ACTION_STUB}/package-lock.json"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  SECOND_DIR="${output##*Installed under: }"
  [ "${FIRST_DIR}" != "${SECOND_DIR}" ]
}

@test "installs into a private staging dir, not the shared cache key" {
  # 共有の鍵ディレクトリを組み立て途中で作ると，同時に走った別プロセスが
  # 未完成の状態を掴む．失敗時の後始末も相手の使用中ディレクトリを消す．
  # 組み立ては専用ディレクトリで行い，完成後に鍵の位置へ移す．
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  PUBLISHED="${output##*Installed under: }"
  INSTALLED_IN="$(cat "${NPM_CWD_LOG}")"
  [ "${INSTALLED_IN}" != "${PUBLISHED}" ]
  [[ "$(basename "${INSTALLED_IN}")" == .staging.* ]]
}

@test "publishes nothing to the cache when npm ci fails" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  mkdir -p "${LINT_DEPS_CACHE_DIR}"
  echo "keep me" > "${LINT_DEPS_CACHE_DIR}/sentinel"
  export NPM_CI_EXIT=1

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
  [ -f "${LINT_DEPS_CACHE_DIR}/sentinel" ]
  # 未完成のキャッシュを残さない．
  run find "${LINT_DEPS_CACHE_DIR}" -name "node_modules" -maxdepth 2
  [ -z "${output}" ]
}

@test "leaves no staging directory behind on success" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"

  run bash "${SCRIPT}"
  [ "${status}" -eq 0 ]

  run find "${LINT_DEPS_CACHE_DIR}" -maxdepth 1 -name ".staging.*"
  [ -z "${output}" ]
}

@test "never nests the staging tree under an already claimed cache key" {
  # 存在検査のあとで rename すると，先に公開した側のディレクトリ配下へ
  # 自分の組み立て先が丸ごと入り，mv は成功を返す．重複した依存一式が
  # 消えないまま残る．公開は上書きしない操作で行う必要がある．
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  KEY_DIR="${LINT_DEPS_CACHE_DIR}/$(cache_key)"
  mkdir -p "${KEY_DIR}"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  run find "${KEY_DIR}" -name ".staging.*"
  [ -z "${output}" ]
}

@test "uses its own install when the cache key is claimed by another run" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  KEY_DIR="${LINT_DEPS_CACHE_DIR}/$(cache_key)"
  mkdir -p "${KEY_DIR}"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  INSTALLED_DIR="${output##*Installed under: }"
  [ -d "${INSTALLED_DIR}/node_modules/.bin" ]
}

@test "adopts a cache published by a concurrent run" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  KEY_DIR="${LINT_DEPS_CACHE_DIR}/$(cache_key)"
  mkdir -p "${KEY_DIR}"
  # 競合相手が公開を完了する状況を作る．
  export RIVAL_PUBLISH_DIR="${KEY_DIR}"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q "^bin=${KEY_DIR}/node_modules/.bin$" "${GITHUB_OUTPUT}"
  run find "${LINT_DEPS_CACHE_DIR}" -maxdepth 1 -name ".staging.*"
  [ -z "${output}" ]
}

@test "releases the cache key when publishing fails" {
  # 確保したまま公開に失敗すると，鍵の位置が空のまま残る．以後の実行は
  # すべて mkdir に失敗し，現れない .bin を待ってから自前の導入へ落ちる．
  # 掃除は .staging.* しか見ないため，この鍵は自動では復旧しない．
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  KEY_DIR="${LINT_DEPS_CACHE_DIR}/$(cache_key)"
  # 公開の mv だけを失敗させる．
  cat > "${FAKE_BIN}/mv" <<'FAKE'
#!/usr/bin/env bash
exit 1
FAKE
  chmod +x "${FAKE_BIN}/mv"

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
  [ ! -e "${KEY_DIR}" ]
}

@test "still succeeds when the cache key path is a regular file" {
  export LINT_DEPS_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"
  mkdir -p "${LINT_DEPS_CACHE_DIR}"
  echo "blocked" > "${LINT_DEPS_CACHE_DIR}/$(cache_key)"

  run bash "${SCRIPT}"

  # 公開できなくても導入自体は完了している．壊れた成果は返さない．
  [ "${status}" -eq 0 ]
  INSTALLED_DIR="${output##*Installed under: }"
  [ -d "${INSTALLED_DIR}/node_modules/.bin" ]
}

@test "falls back to RUNNER_TEMP when LINT_DEPS_CACHE_DIR is empty" {
  export LINT_DEPS_CACHE_DIR=""

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  INSTALLED_DIR="${output##*Installed under: }"
  [[ "${INSTALLED_DIR}" == "${RUNNER_TEMP}/"* ]]
}
