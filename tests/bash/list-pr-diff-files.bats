#!/usr/bin/env bats

# scripts/list-pr-diff-files.sh の単体テスト．
#
# 仕様:
#   入力（環境変数）
#     GH_TOKEN  - GitHub token（必須）
#     REPO      - owner/repo（必須）
#     PR_NUMBER - PR 番号（必須）
#   動作
#     - GET /repos/:owner/:repo/pulls/:pr/files?per_page=100 を叩き，
#       各要素の filename を 1 行ずつ stdout に出す
#     - Link ヘッダの rel="next" で全ページを辿る
#     - 必須 env が欠ければ非 0 終了（execution error）
#     - GET 失敗（非 2xx）時は ::warning:: を stderr に出し非 0 終了
#       （Issue #59: 失敗時は「差分ファイル 0 件」と誤解釈させず，呼び出し側で
#       repo-wide スコープへのフォールバック判断ができるようにするため）
#
# テスト戦略:
#   post-lint-summary.bats と同様，実 API を叩かないため fake curl を
#   PATH 前段に仕込む．

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/list-pr-diff-files.sh"

  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  mkdir -p "${FAKE_BIN}"
  cat > "${FAKE_BIN}/curl" <<'FAKE'
#!/usr/bin/env bash
out_file=""
hdr_file=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) out_file="$2"; shift 2;;
    -D) hdr_file="$2"; shift 2;;
    -w) shift 2;;
    -H) shift 2;;
    --retry|--max-time) shift 2;;
    -sS|--retry-all-errors) shift;;
    http*) url="$1"; shift;;
    *) shift;;
  esac
done

if [ -n "${FAKE_CURL_LOG:-}" ]; then
  printf 'GET %s\n' "${url}" >> "${FAKE_CURL_LOG}"
fi

counter_file="${FAKE_CURL_PAGE_COUNTER:-${BATS_TEST_TMPDIR}/page-counter}"
n="$(cat "${counter_file}" 2>/dev/null || echo 0)"
n=$((n + 1))
echo "${n}" > "${counter_file}"

body_var="FAKE_CURL_GET_BODY_PAGE_${n}"
body="${!body_var:-${FAKE_CURL_GET_BODY:-[]}}"
status="${FAKE_CURL_GET_STATUS:-200}"

link_var="FAKE_CURL_GET_LINK_PAGE_${n}"
link="${!link_var:-}"

[ -n "${out_file}" ] && printf '%s' "${body}" > "${out_file}"
if [ -n "${hdr_file}" ]; then
  if [ -n "${link}" ]; then
    printf 'HTTP/2 %s\r\nLink: %s\r\n\r\n' "${status}" "${link}" > "${hdr_file}"
  else
    printf 'HTTP/2 %s\r\n\r\n' "${status}" > "${hdr_file}"
  fi
fi
printf '%s' "${status}"
exit 0
FAKE
  chmod +x "${FAKE_BIN}/curl"
  PATH="${FAKE_BIN}:${PATH}"
  export PATH

  export GH_TOKEN="fake-token"
  export REPO="acme/repo"
  export PR_NUMBER="42"
  export FAKE_CURL_LOG="${BATS_TEST_TMPDIR}/curl.log"
}

teardown() {
  unset GH_TOKEN REPO PR_NUMBER FAKE_CURL_LOG
  unset FAKE_CURL_GET_STATUS FAKE_CURL_GET_BODY
  unset FAKE_CURL_GET_BODY_PAGE_1 FAKE_CURL_GET_BODY_PAGE_2
  unset FAKE_CURL_GET_LINK_PAGE_1 FAKE_CURL_GET_LINK_PAGE_2
}

@test "PR ファイル一覧を 1 行 1 ファイルで stdout に出す" {
  export FAKE_CURL_GET_BODY='[{"filename":"docs/a.md"},{"filename":"docs/b.md"}]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${lines[0]}" = "docs/a.md" ]
  [ "${lines[1]}" = "docs/b.md" ]
  grep -q '^GET https://api\.github\.com/repos/acme/repo/pulls/42/files' "${FAKE_CURL_LOG}"
}

@test "空配列のときは空出力で正常終了する" {
  export FAKE_CURL_GET_BODY='[]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ -z "${output}" ]
}

@test "Link ヘッダ next で全ページを辿り filename を結合する" {
  export FAKE_CURL_GET_BODY_PAGE_1='[{"filename":"a.md"}]'
  export FAKE_CURL_GET_LINK_PAGE_1='<https://api.github.com/page2>; rel="next"'
  export FAKE_CURL_GET_BODY_PAGE_2='[{"filename":"b.md"}]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${lines[0]}" = "a.md" ]
  [ "${lines[1]}" = "b.md" ]
  [ "$(grep -c '^GET ' "${FAKE_CURL_LOG}")" -eq 2 ]
}

@test "GET 失敗時は ::warning:: を出し非 0 終了する" {
  export FAKE_CURL_GET_STATUS=503

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
  [[ "${output}" == *"::warning::"* ]]
}

@test "GH_TOKEN 未設定で execution error として非 0 終了" {
  unset GH_TOKEN

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "REPO 未設定で execution error として非 0 終了" {
  unset REPO

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "PR_NUMBER 未設定で execution error として非 0 終了" {
  unset PR_NUMBER

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}
