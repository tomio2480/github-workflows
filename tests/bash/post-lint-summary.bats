#!/usr/bin/env bats

# scripts/post-lint-summary.sh の単体テスト．
#
# 仕様:
#   入力（環境変数）
#     GH_TOKEN     - GitHub token（必須）
#     REPO         - owner/repo（必須）
#     PR_NUMBER    - PR 番号（必須）
#     SUMMARY_JSON - count-lint-findings.py が出した JSON ファイルのパス（必須）
#   動作
#     - <!-- gh-workflows-lint-summary --> を marker として既存コメントを GET → find
#     - 一致あれば PATCH /repos/:owner/:repo/issues/comments/:id
#     - 一致なければ POST /repos/:owner/:repo/issues/:pr/comments
#     - 必須 env が欠ければ非 0 終了（execution error）
#     - GET / POST / PATCH 失敗時は ::warning:: + exit 0（fail-open）
#     - コメント本文には marker / ツール名 / 件数（または "指摘はありません．"）が含まれる
#
# テスト戦略:
#   - 実 API を叩かないため fake curl を PATH 前段に仕込む
#   - fake curl は -X METHOD で分岐し，メソッドごとに status / body を切替
#   - リクエスト記録を FAKE_CURL_LOG ファイルに残し，呼ばれたメソッドと URL，
#     送信された JSON 本文を assertion できるようにする

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/post-lint-summary.sh"

  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  mkdir -p "${FAKE_BIN}"
  cat > "${FAKE_BIN}/curl" <<'FAKE'
#!/usr/bin/env bash
# テスト用 fake curl．本物の curl の引数体系のうちスクリプトが使う組合せだけ
# 解釈する．
#   -X METHOD      明示メソッド（GET / POST / PATCH）
#   -o FILE        body 出力先
#   -D FILE        ヘッダ出力先
#   -w FORMAT      stdout に出すフォーマット（%{http_code} のみ想定）
#   --data-binary  リクエスト本文．@FILE 形式に対応
#   URL            最後の引数として URL
method="GET"
out_file=""
hdr_file=""
data=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -X)
      method="$2"; shift 2;;
    -o)
      out_file="$2"; shift 2;;
    -D)
      hdr_file="$2"; shift 2;;
    -w)
      shift 2;;
    --data-binary)
      data="$2"; shift 2;;
    -H)
      shift 2;;
    --retry|--max-time)
      shift 2;;
    -sS|--retry-all-errors)
      shift;;
    http*)
      url="$1"; shift;;
    *)
      shift;;
  esac
done

if [ -n "${FAKE_CURL_LOG:-}" ]; then
  printf '%s %s\n' "${method}" "${url}" >> "${FAKE_CURL_LOG}"
  if [ "${data:0:1}" = "@" ]; then
    payload_file="${data:1}"
    printf 'BODY: ' >> "${FAKE_CURL_LOG}"
    cat "${payload_file}" >> "${FAKE_CURL_LOG}"
    printf '\n' >> "${FAKE_CURL_LOG}"
  elif [ -n "${data}" ]; then
    printf 'BODY: %s\n' "${data}" >> "${FAKE_CURL_LOG}"
  fi
fi

case "${method}" in
  GET)
    body="${FAKE_CURL_GET_BODY:-[]}"
    status="${FAKE_CURL_GET_STATUS:-200}"
    ;;
  POST)
    body="${FAKE_CURL_POST_BODY:-{\"id\":1}}"
    status="${FAKE_CURL_POST_STATUS:-201}"
    ;;
  PATCH)
    body="${FAKE_CURL_PATCH_BODY:-{\"id\":1}}"
    status="${FAKE_CURL_PATCH_STATUS:-200}"
    ;;
  *)
    body=""
    status="500"
    ;;
esac

[ -n "${out_file}" ] && printf '%s' "${body}" > "${out_file}"
if [ -n "${hdr_file}" ]; then
  printf 'HTTP/2 %s\r\n\r\n' "${status}" > "${hdr_file}"
fi
printf '%s' "${status}"
exit "${FAKE_CURL_EXIT:-0}"
FAKE
  chmod +x "${FAKE_BIN}/curl"
  PATH="${FAKE_BIN}:${PATH}"
  export PATH

  export GH_TOKEN="fake-token"
  export REPO="acme/repo"
  export PR_NUMBER="42"
  export FAKE_CURL_LOG="${BATS_TEST_TMPDIR}/curl.log"

  SUMMARY_JSON_FILE="${BATS_TEST_TMPDIR}/summary.json"
  export SUMMARY_JSON="${SUMMARY_JSON_FILE}"
}

teardown() {
  unset FAKE_CURL_GET_STATUS FAKE_CURL_GET_BODY
  unset FAKE_CURL_POST_STATUS FAKE_CURL_POST_BODY
  unset FAKE_CURL_PATCH_STATUS FAKE_CURL_PATCH_BODY
  unset FAKE_CURL_EXIT FAKE_CURL_LOG
  unset GH_TOKEN REPO PR_NUMBER SUMMARY_JSON
}

_write_summary() {
  printf '%s' "$1" > "${SUMMARY_JSON_FILE}"
}

@test "既存コメントなしのとき POST で新規作成し marker と本文を含む" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_GET_BODY='[]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q '^GET https://api\.github\.com/repos/acme/repo/issues/42/comments' "${FAKE_CURL_LOG}"
  grep -q '^POST https://api\.github\.com/repos/acme/repo/issues/42/comments$' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*gh-workflows-lint-summary' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*指摘はありません' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*markdownlint' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*textlint' "${FAKE_CURL_LOG}"
}

@test "marker 付きコメントが既にあるとき PATCH で更新する" {
  _write_summary '{"markdownlint":{"total":3,"findings":[{"file":"a.md","line":1,"rule":"MD041/x","message":"top heading"}]},"textlint":{"error":1,"warning":2,"info":0,"total":3,"findings":[{"file":"a.md","line":2,"severity":"error","rule":"r1","message":"bad"}]}}'
  export FAKE_CURL_GET_BODY='[{"id":99,"body":"<!-- gh-workflows-lint-summary -->\nold"}]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q '^PATCH https://api\.github\.com/repos/acme/repo/issues/comments/99$' "${FAKE_CURL_LOG}"
  ! grep -q '^POST ' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*差分行に該当' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*filter-mode' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*markdownlint' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*error: 1' "${FAKE_CURL_LOG}"
  # findings 一覧が details で展開可能な形で含まれる
  grep -q 'BODY: .*<details>' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*a\.md:1' "${FAKE_CURL_LOG}"
}

@test "GITHUB_WORKSPACE 配下の絶対パスは相対パスに正規化されて本文に出る" {
  python3 - "${SUMMARY_JSON_FILE}" <<'PY'
import json
import sys

payload = {
    "markdownlint": {
        "total": 1,
        "findings": [
            {
                "file": "/home/runner/work/repo/repo/docs/foo.md",
                "line": 3,
                "rule": "MD041/first-line-heading",
                "message": "First line heading",
            }
        ],
    },
    "textlint": {
        "error": 0, "warning": 0, "info": 0, "total": 0, "findings": [],
    },
}
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
    json.dump(payload, f, ensure_ascii=False)
PY
  export FAKE_CURL_GET_BODY='[]'
  export GITHUB_WORKSPACE="/home/runner/work/repo/repo"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q 'BODY: .*`docs/foo\.md:3`' "${FAKE_CURL_LOG}"
  ! grep -q 'BODY: .*`/home/runner' "${FAKE_CURL_LOG}"

  unset GITHUB_WORKSPACE
}

@test "message 内の改行はスペースに畳まれて 1 行に表示される" {
  python3 - "${SUMMARY_JSON_FILE}" <<'PY'
import json
import sys

payload = {
    "markdownlint": {"total": 0, "findings": []},
    "textlint": {
        "error": 1, "warning": 0, "info": 0, "total": 1,
        "findings": [
            {
                "file": "docs/foo.md",
                "line": 5,
                "severity": "error",
                "rule": "prh",
                "message": "first line\nsecond line\rthird line",
            }
        ],
    },
}
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
    json.dump(payload, f, ensure_ascii=False)
PY
  export FAKE_CURL_GET_BODY='[]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  # 改行が含まれた message でも，1 件分が 1 行で表現されている
  grep -q 'BODY: .*first line second line third line' "${FAKE_CURL_LOG}"
  # body 中に「裸の改行」 の中継表現（リテラル \n や \r）が残っていない
  ! grep -Pq 'BODY: .*first line\\n' "${FAKE_CURL_LOG}"
}

@test "textlint の eslint.rules. プレフィックスは表示時に剥がされる" {
  python3 - "${SUMMARY_JSON_FILE}" <<'PY'
import json
import sys

payload = {
    "markdownlint": {"total": 0, "findings": []},
    "textlint": {
        "error": 1, "warning": 0, "info": 0, "total": 1,
        "findings": [
            {
                "file": "docs/foo.md",
                "line": 5,
                "severity": "error",
                "rule": "eslint.rules.prh",
                "message": "Github => GitHub",
            }
        ],
    },
}
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
    json.dump(payload, f, ensure_ascii=False)
PY
  export FAKE_CURL_GET_BODY='[]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q 'BODY: .*\[error\] prh:' "${FAKE_CURL_LOG}"
  ! grep -q 'BODY: .*eslint\.rules\.prh' "${FAKE_CURL_LOG}"
}

@test "Actions run の env が揃っていれば本文に Actions run リンクを含む" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_GET_BODY='[]'
  export GITHUB_SERVER_URL="https://github.com"
  export GITHUB_REPOSITORY="acme/repo"
  export GITHUB_RUN_ID="9999"
  export GITHUB_RUN_ATTEMPT="1"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q 'BODY: .*Actions run: https://github\.com/acme/repo/actions/runs/9999/attempts/1' "${FAKE_CURL_LOG}"

  unset GITHUB_SERVER_URL GITHUB_REPOSITORY GITHUB_RUN_ID GITHUB_RUN_ATTEMPT
}

@test "findings が MAX を超えるとき details 末尾に「他 X 件」 と出る" {
  # MAX_FINDINGS_PER_TOOL は 20．25 件渡して切り詰めを確認．
  python3 - "${SUMMARY_JSON_FILE}" <<'PY'
import json
import sys

findings = [
    {"file": f"f{i}.md", "line": i, "severity": "error", "rule": "r", "message": "msg"}
    for i in range(1, 26)
]
payload = {
    "markdownlint": {"total": 0, "findings": []},
    "textlint": {"error": 25, "warning": 0, "info": 0, "total": 25, "findings": findings},
}
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as f:
    json.dump(payload, f, ensure_ascii=False)
PY
  export FAKE_CURL_GET_BODY='[]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q 'BODY: .*他 5 件' "${FAKE_CURL_LOG}"
}

@test "他人のコメントのみで marker が無いときは POST する" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_GET_BODY='[{"id":7,"body":"<!-- coderabbit-summary -->"},{"id":8,"body":"comment without marker"}]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q '^POST ' "${FAKE_CURL_LOG}"
  ! grep -q '^PATCH ' "${FAKE_CURL_LOG}"
}

@test "GET 失敗時は ::warning:: で fail-open（exit 0）" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_GET_STATUS=503

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"::warning::"* ]]
  ! grep -q '^POST ' "${FAKE_CURL_LOG}"
  ! grep -q '^PATCH ' "${FAKE_CURL_LOG}"
}

@test "POST 失敗時は ::warning:: で fail-open（exit 0）" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_GET_BODY='[]'
  export FAKE_CURL_POST_STATUS=422
  export FAKE_CURL_POST_BODY='{"message":"Validation Failed"}'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"::warning::"* ]]
  [[ "${output}" == *"Validation Failed"* ]]
}

@test "GH_TOKEN 未設定で execution error として非 0 終了" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  unset GH_TOKEN

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "REPO 未設定で execution error として非 0 終了" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  unset REPO

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "PR_NUMBER 未設定で execution error として非 0 終了" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  unset PR_NUMBER

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "SUMMARY_JSON 未設定で execution error として非 0 終了" {
  unset SUMMARY_JSON

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "PATCH 失敗時は ::warning:: で fail-open（exit 0）" {
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_GET_BODY='[{"id":99,"body":"<!-- gh-workflows-lint-summary -->\nold"}]'
  export FAKE_CURL_PATCH_STATUS=502
  export FAKE_CURL_PATCH_BODY='{"message":"Bad Gateway"}'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"::warning::"* ]]
  [[ "${output}" == *"Bad Gateway"* ]]
  grep -q '^PATCH ' "${FAKE_CURL_LOG}"
}

@test "Link ヘッダ next で pagination を辿り 2 ページ目で marker を発見したら PATCH" {
  # FAKE_CURL_GET_BODY を fake curl 内のカウンタで分岐させる．
  # 1 回目: 空配列 + Link ヘッダ next，2 回目: marker 入り 1 件．
  _write_summary '{"markdownlint":{"total":0},"textlint":{"error":0,"warning":0,"info":0,"total":0}}'
  export FAKE_CURL_PAGINATE_DIR="${BATS_TEST_TMPDIR}/paginate"
  mkdir -p "${FAKE_CURL_PAGINATE_DIR}"

  # fake curl を pagination 対応に差し替える．
  cat > "${FAKE_BIN}/curl" <<'FAKE'
#!/usr/bin/env bash
method="GET"
out_file=""
hdr_file=""
data=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -X) method="$2"; shift 2;;
    -o) out_file="$2"; shift 2;;
    -D) hdr_file="$2"; shift 2;;
    -w) shift 2;;
    --data-binary) data="$2"; shift 2;;
    -H) shift 2;;
    --retry|--max-time) shift 2;;
    -sS|--retry-all-errors) shift;;
    http*) url="$1"; shift;;
    *) shift;;
  esac
done

[ -n "${FAKE_CURL_LOG:-}" ] && printf '%s %s\n' "${method}" "${url}" >> "${FAKE_CURL_LOG}"

case "${method}" in
  GET)
    counter_file="${FAKE_CURL_PAGINATE_DIR:-/tmp}/get-counter"
    n="$(cat "${counter_file}" 2>/dev/null || echo 0)"
    n=$((n + 1))
    echo "${n}" > "${counter_file}"
    if [ "${n}" = "1" ]; then
      body='[]'
      printf 'HTTP/2 200\r\nLink: <https://api.github.com/page2>; rel="next"\r\n\r\n' > "${hdr_file}"
    else
      body='[{"id":77,"body":"<!-- gh-workflows-lint-summary -->\nfound on page 2"}]'
      printf 'HTTP/2 200\r\n\r\n' > "${hdr_file}"
    fi
    status=200
    ;;
  PATCH)
    body='{"id":77}'
    status=200
    ;;
  *)
    body=''
    status=500
    ;;
esac

[ -n "${out_file}" ] && printf '%s' "${body}" > "${out_file}"
printf '%s' "${status}"
exit 0
FAKE
  chmod +x "${FAKE_BIN}/curl"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  # 2 回 GET したことを確認
  [ "$(grep -c '^GET ' "${FAKE_CURL_LOG}")" -eq 2 ]
  # 2 ページ目で見つかった ID 77 で PATCH したことを確認
  grep -q '^PATCH https://api\.github\.com/repos/acme/repo/issues/comments/77$' "${FAKE_CURL_LOG}"
}

@test "件数ありの textlint で内訳がコメント本文に出る" {
  _write_summary '{"markdownlint":{"total":2},"textlint":{"error":3,"warning":4,"info":1,"total":8}}'
  export FAKE_CURL_GET_BODY='[]'

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q 'BODY: .*markdownlint.*2' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*textlint.*8' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*error: 3' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*warning: 4' "${FAKE_CURL_LOG}"
  grep -q 'BODY: .*info: 1' "${FAKE_CURL_LOG}"
}
