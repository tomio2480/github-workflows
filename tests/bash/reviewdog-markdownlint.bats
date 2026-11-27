#!/usr/bin/env bats

# scripts/reviewdog-markdownlint.sh unit tests.
#
# Spec:
#   Usage: reviewdog-markdownlint.sh <report> [extra reviewdog args...]
#   Behavior:
#     - Runs reviewdog with the markdownlint errorformat list and -name=markdownlint
#     - The errorformat list skips the severity word (error / warning) that
#       markdownlint-cli2 0.24 inserts between the position and the rule,
#       and still accepts the older format without it
#     - Appends the extra arguments after the fixed ones
#     - Feeds the report file to reviewdog on stdin
#     - Propagates the exit code of reviewdog
#     - Exits non-zero without running reviewdog when the report argument is missing
#
# Test strategy:
#   Inject a fake reviewdog into PATH that records its argv and stdin.

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/reviewdog-markdownlint.sh"
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  mkdir -p "${FAKE_BIN}"

  export ARGS_LOG="${BATS_TEST_TMPDIR}/args"
  export STDIN_LOG="${BATS_TEST_TMPDIR}/stdin"
  cat >"${FAKE_BIN}/reviewdog" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$@" >"${ARGS_LOG}"
cat >"${STDIN_LOG}"
exit "${REVIEWDOG_EXIT:-0}"
FAKE
  chmod +x "${FAKE_BIN}/reviewdog"
  PATH="${FAKE_BIN}:${PATH}"
  export PATH

  REPORT="${BATS_TEST_TMPDIR}/markdownlint-report.txt"
  printf '%s\n' \
    'markdownlint-cli2 v0.24.2 (markdownlint v0.42.2)' \
    'docs/a.md:3 error MD012/no-multiple-blanks Multiple consecutive blank lines' >"${REPORT}"
}

@test "passes the errorformat list that skips the severity word" {
  run bash "${SCRIPT}" "${REPORT}"
  [ "${status}" -eq 0 ]
  [ "$(sed -n 1p "${ARGS_LOG}")" = "-efm=%f:%l:%c %*[a-z] %m" ]
  [ "$(sed -n 2p "${ARGS_LOG}")" = "-efm=%f:%l %*[a-z] %m" ]
  [ "$(sed -n 3p "${ARGS_LOG}")" = "-efm=%f:%l:%c %m" ]
  [ "$(sed -n 4p "${ARGS_LOG}")" = "-efm=%f:%l %m" ]
  [ "$(sed -n 5p "${ARGS_LOG}")" = "-name=markdownlint" ]
}

@test "appends the extra reviewdog arguments after the fixed ones" {
  run bash "${SCRIPT}" "${REPORT}" -reporter=local -filter-mode=nofilter
  [ "${status}" -eq 0 ]
  [ "$(sed -n 6p "${ARGS_LOG}")" = "-reporter=local" ]
  [ "$(sed -n 7p "${ARGS_LOG}")" = "-filter-mode=nofilter" ]
  [ "$(wc -l <"${ARGS_LOG}")" -eq 7 ]
}

@test "feeds the report to reviewdog on stdin" {
  run bash "${SCRIPT}" "${REPORT}"
  [ "${status}" -eq 0 ]
  cmp -s "${REPORT}" "${STDIN_LOG}"
}

@test "propagates the exit code of reviewdog" {
  REVIEWDOG_EXIT=1 run bash "${SCRIPT}" "${REPORT}"
  [ "${status}" -eq 1 ]
}

@test "fails without running reviewdog when the report argument is missing" {
  run bash "${SCRIPT}"
  [ "${status}" -ne 0 ]
  [ ! -e "${ARGS_LOG}" ]
}
