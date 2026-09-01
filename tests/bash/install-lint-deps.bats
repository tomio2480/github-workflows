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

  cat > "${FAKE_BIN}/npm" <<'FAKE'
#!/usr/bin/env bash
case "$1" in
  ci)
    mkdir -p "./node_modules/.bin"
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

teardown() {
  unset ACTION_PATH RUNNER_TEMP GITHUB_OUTPUT NPM_CI_EXIT LINT_DEPS_CACHE_DIR
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

@test "falls back to RUNNER_TEMP when LINT_DEPS_CACHE_DIR is empty" {
  export LINT_DEPS_CACHE_DIR=""

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  INSTALLED_DIR="${output##*Installed under: }"
  [[ "${INSTALLED_DIR}" == "${RUNNER_TEMP}/"* ]]
}
