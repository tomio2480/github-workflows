#!/usr/bin/env bats

# scripts/install-textlint-deps.sh unit tests.
#
# Spec:
#   Input (environment variables):
#     ACTION_PATH   - absolute path to the action dir (holds package.json / package-lock.json) [required]
#     RUNNER_TEMP   - base dir for tmpdir creation [required]
#     GITHUB_OUTPUT - GitHub Actions output file path [required]
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
  SCRIPT="${REPO_ROOT}/scripts/install-textlint-deps.sh"
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
  unset ACTION_PATH RUNNER_TEMP GITHUB_OUTPUT NPM_CI_EXIT
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
