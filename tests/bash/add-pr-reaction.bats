#!/usr/bin/env bats

# scripts/add-pr-reaction.sh の単体テスト．
#
# 仕様:
#   入力（環境変数）
#     GH_TOKEN  - GitHub token（必須）
#     REPO      - owner/repo（必須）
#     PR_NUMBER - PR 番号（必須）
#   動作
#     - 同名 user × 同名 content (eyes) で idempotent な GitHub Reactions API を
#       POST する．retry / timeout は curl オプションで吸収．
#     - HTTP 2xx で成功とみなし stdout に成功メッセージ
#     - 非 2xx もしくは curl 自体の失敗時は ::warning:: 形式で annotation 化し
#       レスポンスボディを cat するが exit 0 (fail-open)
#     - 必須 env が欠けている場合は非 0 終了（execution error）
#
# テスト戦略:
#   - 実 API を叩かないため，PATH の前段に fake curl を仕込んでネットワーク呼び出しを
#     差し替える．fake curl は FAKE_CURL_STATUS / FAKE_CURL_BODY / FAKE_CURL_EXIT で
#     挙動を切り替える．

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/add-pr-reaction.sh"
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  mkdir -p "${FAKE_BIN}"
  cat > "${FAKE_BIN}/curl" <<'FAKE'
#!/usr/bin/env bash
# テスト用 fake curl．本物の curl と同じ「-o <file> に body を書き，stdout に
# %{http_code} の値（=想定 HTTP ステータス）を出す」挙動を最小限再現する．
out_file=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o)
      out_file="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done
if [ -n "${out_file}" ]; then
  printf '%s' "${FAKE_CURL_BODY:-}" > "${out_file}"
fi
printf '%s' "${FAKE_CURL_STATUS:-200}"
exit "${FAKE_CURL_EXIT:-0}"
FAKE
  chmod +x "${FAKE_BIN}/curl"
  PATH="${FAKE_BIN}:${PATH}"
  export PATH
  # 既定の必須 env．個別テストで上書き可能．
  export GH_TOKEN="fake-token"
  export REPO="acme/repo"
  export PR_NUMBER="42"
}

teardown() {
  unset FAKE_CURL_STATUS FAKE_CURL_BODY FAKE_CURL_EXIT
  unset GH_TOKEN REPO PR_NUMBER
}

@test "exit 0 で成功メッセージを出す（HTTP 200）" {
  export FAKE_CURL_STATUS=200

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"Added 👀 reaction to PR #42"* ]]
  [[ "${output}" == *"(HTTP 200)"* ]]
}

@test "exit 0 で成功メッセージを出す（HTTP 201 = 新規作成）" {
  export FAKE_CURL_STATUS=201

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"Added 👀 reaction to PR #42"* ]]
  [[ "${output}" == *"(HTTP 201)"* ]]
}

@test "非 2xx は ::warning:: で annotation 化しレスポンスを cat（exit 0 = fail-open）" {
  export FAKE_CURL_STATUS=422
  export FAKE_CURL_BODY='{"message":"Validation Failed"}'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"::warning::Failed to add 👀 reaction"* ]]
  [[ "${output}" == *"(HTTP 422)"* ]]
  [[ "${output}" == *"Validation Failed"* ]]
}

@test "curl 自体の失敗を curl-error として扱う（exit 0 = fail-open）" {
  export FAKE_CURL_EXIT=7

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"::warning::Failed to add 👀 reaction"* ]]
  [[ "${output}" == *"(HTTP curl-error)"* ]]
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
