#!/usr/bin/env bash

# PR の checks が出そろうまで監視する（Issue #133）．
#
# 契約は docs/watch-pr-checks.md，設計判断は
# docs/notes/2026-09-03-issue133-watch-pr-checks.md を参照する．
#
# 終了コード:
#   0  観測した checks に fail・cancel がない（すべて skip の場合を含む）
#   1  入力エラー・環境エラー
#   2  タイムアウト，または監視対象 commit の不一致
#   3  checks が pass しなかった

set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: watch-pr-checks.sh <pr-number> [--timeout SECONDS] [--interval SECONDS]
                          [--settle SECONDS] [--expect-sha SHA]
                          [--format full|summary|json] [--limit N] [--output-dir DIR]

  pr-number      監視する PR の番号
  --timeout      監視全体のタイムアウト秒（既定: 600）．段ごとに取り直さない
  --interval     ポーリング間隔秒（既定: 10）
  --settle       件数が動かなくなってから完了と見なすまでの秒数（既定: 120）
  --expect-sha   監視対象 commit を明示する（40 桁）．origin への問い合わせを省く
  --format       full（既定）・summary・json．後二者は観測記録を保存する
  --limit        要約へ載せる check の上限（既定: 20）
  --output-dir   実行別フォルダの親．full でも保存する．記録には Python 3.9+ が必要
USAGE
  exit 1
}

PR="${1:-}"
[ $# -ge 1 ] || usage
shift

TIMEOUT=600
INTERVAL=10
SETTLE=120
EXPECT_SHA=""
FORMAT=full
LIMIT=20
OUTPUT_DIR=""
RUN_DIR=""
REASON=error
LAST_ERR=""
CALL_ERR=""

# 値必須オプションが後続オプションを値として吸うと，指定の欠落が既定値へ
# 化けて気づけないため，ハイフン始まりと空値を拒否する
require_value() {
  if [ -z "${2:-}" ] || [[ "${2}" == -* ]]; then
    echo "error: $1 requires a value" >&2
    exit 1
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --timeout)
      require_value --timeout "${2:-}"
      TIMEOUT="$2"
      shift 2
      ;;
    --interval)
      require_value --interval "${2:-}"
      INTERVAL="$2"
      shift 2
      ;;
    --settle)
      require_value --settle "${2:-}"
      SETTLE="$2"
      shift 2
      ;;
    --expect-sha)
      require_value --expect-sha "${2:-}"
      EXPECT_SHA="$2"
      shift 2
      ;;
    --format)
      require_value --format "${2:-}"
      FORMAT="$2"
      shift 2
      ;;
    --limit)
      require_value --limit "${2:-}"
      LIMIT="$2"
      shift 2
      ;;
    --output-dir)
      require_value --output-dir "${2:-}"
      OUTPUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage
      ;;
  esac
done

# --- 入力検証 ---

if ! [[ "${PR}" =~ ^[0-9]+$ ]]; then
  echo "error: pr-number must be a positive integer: ${PR}" >&2
  exit 1
fi

if ! [[ "${TIMEOUT}" =~ ^[0-9]+$ ]]; then
  echo "error: --timeout must be a non-negative integer: ${TIMEOUT}" >&2
  exit 1
fi

if ! [[ "${INTERVAL}" =~ ^[0-9]+$ ]]; then
  echo "error: --interval must be a non-negative integer: ${INTERVAL}" >&2
  exit 1
fi

if ! [[ "${SETTLE}" =~ ^[0-9]+$ ]]; then
  echo "error: --settle must be a non-negative integer: ${SETTLE}" >&2
  exit 1
fi

# settle が timeout を超えると，どれだけ静かでも必ずタイムアウトする
if [ "${SETTLE}" -gt "${TIMEOUT}" ]; then
  echo "error: --settle (${SETTLE}) must not exceed --timeout (${TIMEOUT})" >&2
  exit 1
fi

# 間隔 0 で据え置きを待つと，その間 API を全速で叩き続ける
if [ "${INTERVAL}" -eq 0 ] && [ "${SETTLE}" -gt 0 ]; then
  echo "error: --interval 0 requires --settle 0 (it would busy-poll the API)" >&2
  exit 1
fi

if [ -n "${EXPECT_SHA}" ] && ! [[ "${EXPECT_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: --expect-sha must be a full 40-hex SHA: ${EXPECT_SHA}" >&2
  exit 1
fi

# --- 監視対象 commit の確定 ---

# shellcheck disable=SC2329 # EXIT trap; contract tests exercise success and failure.
finish_watch() {
  local code=$?
  trap - EXIT
  rm -f "${LAST_ERR}" "${CALL_ERR}"
  if [ -n "${RUN_DIR}" ]; then
    "${PYTHON}" -X utf8 "${RECORDER}" finish --run-dir "${RUN_DIR}" \
      --code "${code}" --reason "${REASON}" --expected-sha "${EXPECT_SHA}" \
      --pr "${PR}" --format "${FORMAT}" --limit "${LIMIT}" || code=$?
  fi
  exit "${code}"
}

if [[ ! "${FORMAT}" =~ ^(full|summary|json)$ ]] || [[ ! "${LIMIT}" =~ ^[0-9]{1,9}$ ]]; then
  echo "error: --format must be full, summary or json; --limit must be 0..999999999" >&2
  exit 1
fi
if [ "${FORMAT}" != full ] || [ -n "${OUTPUT_DIR}" ]; then
  PYTHON=""
  for candidate in python3 python; do
    if command -v "${candidate}" >/dev/null 2>&1 && "${candidate}" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
      PYTHON="${candidate}"
      break
    fi
  done
  [ -n "${PYTHON}" ] || {
    echo 'error: record mode requires Python 3.9+' >&2
    exit 1
  }
  RECORDER="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)/watch-checks-record.py"
  RUN_DIR="$("${PYTHON}" -X utf8 "${RECORDER}" init --output-dir "${OUTPUT_DIR}" \
    --timeout "${TIMEOUT}" --interval "${INTERVAL}" --settle "${SETTLE}")" || exit 1
  RUN_DIR="${RUN_DIR%$'\r'}"
fi
trap finish_watch EXIT
LAST_ERR="$(mktemp)"
CALL_ERR="$(mktemp)"

# 記録は表示の写しであり，full の表示は記録しない呼び出しと同じく逐次に出す．
# 出力先をファイルへ付け替えると，終了まで何も見えず，記録係が書いた
# 診断の流し直しで stderr も変わる．付け替えず，表示と記録へ 2 回書く
shown() {
  [ -z "${RUN_DIR}" ] || [ "${FORMAT}" = full ]
}

say() {
  if [ -n "${RUN_DIR}" ]; then
    printf '%s\n' "$1" >>"${RUN_DIR}/full.txt"
  fi
  if shown; then
    printf '%s\n' "$1"
  fi
}

warn() {
  if [ -n "${RUN_DIR}" ]; then
    printf '%s\n' "$1" >>"${RUN_DIR}/diagnostics.log"
  fi
  if shown; then
    printf '%s\n' "$1" >&2
  fi
}

warn_file() {
  if [ -n "${RUN_DIR}" ]; then
    cat "$1" >>"${RUN_DIR}/diagnostics.log"
  fi
  if shown; then
    cat "$1" >&2
  fi
}

# 記録係は gh の stderr を diagnostics.log へ書き終えている．表示だけを足す
relay_recorded() {
  if shown; then
    cat "$1" >&2
  fi
}

query_gh() {
  local kind="$1"
  shift
  if [ -n "${RUN_DIR}" ]; then
    "${PYTHON}" -X utf8 "${RECORDER}" query "${RUN_DIR}" "${kind}" gh "$@"
  else
    gh "$@"
  fi
}

# gh は push 直後に古い head を返すことがある．遅れない側であるリモートの
# 実体を正とし，gh の側をそこへ追いつかせる．
#
# fork からの PR では head ブランチが origin に無い．同名のブランチが base に
# あると，無関係な commit を掴んだまま待つ．head の所属先を解決してから引く
if [ -z "${EXPECT_SHA}" ]; then
  RESOLVE_CODE=0
  PR_INFO="$(query_gh resolve pr view "${PR}" \
    --json headRefName,isCrossRepository,headRepositoryOwner,headRepository \
    --jq '[.headRefName, (.isCrossRepository | tostring), .headRepositoryOwner.login, .headRepository.name] | @tsv' \
    2>"${CALL_ERR}")" || RESOLVE_CODE=$?
  relay_recorded "${CALL_ERR}"
  [ "${RESOLVE_CODE}" -eq 0 ] || exit 1
  # IFS のタブは空白類のため read では連続を 1 つに詰め，空欄があると列がずれる．
  # cut は詰めないため列の位置が保たれる
  BRANCH="$(printf '%s' "${PR_INFO}" | cut -f1)"
  CROSS_REPO="$(printf '%s' "${PR_INFO}" | cut -f2)"
  HEAD_OWNER="$(printf '%s' "${PR_INFO}" | cut -f3)"
  HEAD_REPO="$(printf '%s' "${PR_INFO}" | cut -f4)"
  if [ -z "${BRANCH}" ]; then
    warn "error: could not resolve the head branch of PR #${PR}"
    exit 1
  fi

  if [ "${CROSS_REPO}" = "true" ]; then
    if [ -z "${HEAD_OWNER}" ] || [ -z "${HEAD_REPO}" ]; then
      warn "error: could not resolve the head repository of PR #${PR}"
      exit 1
    fi
    REMOTE="https://github.com/${HEAD_OWNER}/${HEAD_REPO}.git"
  else
    REMOTE="origin"
  fi

  # 出力なしには「ブランチが無い」と「照会が失敗した」の 2 つがある．
  # パイプで受けると cut の終了コードに隠れ，認証切れが push 忘れへ化ける
  REMOTE_CODE=0
  REMOTE_LINE="$(git ls-remote "${REMOTE}" "refs/heads/${BRANCH}" 2>"${CALL_ERR}")" || REMOTE_CODE=$?
  warn_file "${CALL_ERR}"
  if [ "${REMOTE_CODE}" -ne 0 ]; then
    warn "error: git ls-remote ${REMOTE} failed while resolving ${BRANCH}"
    exit 1
  fi
  EXPECT_SHA="$(printf '%s\n' "${REMOTE_LINE}" | cut -f1)"
  if [ -z "${EXPECT_SHA}" ]; then
    warn "error: branch ${BRANCH} not found on ${REMOTE} (push it first)"
    exit 1
  fi
  say "watch-pr-checks: target commit ${EXPECT_SHA} (branch ${BRANCH} on ${REMOTE})"
else
  say "watch-pr-checks: target commit ${EXPECT_SHA}"
fi

# --- 問い合わせ ---

# gh の失敗を「条件未成立」と区別できないまま待ち続けると，認証切れが
# 単なるタイムアウトに見える．最後の stderr を残してタイムアウト時に示す．
# 保持するのは「最後に観測した失敗」とする．後続の成功で消さない．
# 直後の 1 回が成功しただけで原因が消えると，追跡できないためである
keep_error() {
  if [ -s "${CALL_ERR}" ]; then
    cat "${CALL_ERR}" >"${LAST_ERR}"
  fi
}

gh_head_oid() {
  query_gh head pr view "${PR}" --json headRefOid --jq .headRefOid 2>"${CALL_ERR}" || true
  keep_error
}

gh_head_matches() {
  [ "$(gh_head_oid)" = "${EXPECT_SHA}" ]
}

# pending・failure でも gh は結果を出しつつ非 0 で終える（pending は exit 8）．
# 終了コードで判定すると検査中の PR を照会失敗と誤読するため，出力だけを見る．
# 出力が無い状態は「未登録」と「照会失敗」の両方を含み，どちらも待機を続ける
checks_buckets() {
  if [ -n "${RUN_DIR}" ]; then
    query_gh checks pr checks "${PR}" --json name,state,bucket,link 2>"${CALL_ERR}" || true
  else
    gh pr checks "${PR}" --json name,state,bucket --jq '.[].bucket' 2>"${CALL_ERR}" || true
  fi
  keep_error
}

# --timeout は監視全体に掛かる．段ごとに取り直すと合計が 2 倍になりうるため，
# 締切は 1 度だけ決めて両方の待機で使い回す
DEADLINE=$(($(date +%s) + TIMEOUT))

report_timeout() {
  REASON=timeout
  warn "error: timed out waiting for $1 (commit ${EXPECT_SHA})"
  if [ -s "${LAST_ERR}" ]; then
    warn "error: last gh error was:"
    warn_file "${LAST_ERR}"
  fi
  exit 2
}

# --- gh がリモートへ追いつくのを待つ ---

say "watch-pr-checks: waiting for gh to catch up with the remote"
while ! gh_head_matches; do
  if [ "$(date +%s)" -ge "${DEADLINE}" ]; then
    report_timeout "gh to report the target commit"
  fi
  if [ "${INTERVAL}" -gt 0 ]; then
    sleep "${INTERVAL}"
  fi
done

# --- checks が出そろうのを待つ ---

# 登録の遅れを吸収するため，件数が一定の時間を要求する．
# settle 後の未登録 check まで検査したという保証にはならない．
say "watch-pr-checks: waiting for checks to settle"
PREV_TOTAL=-1
PREV_REPORT=""
STABLE_SINCE="$(date +%s)"
while :; do
  BUCKETS="$(checks_buckets)"
  TOTAL=0
  PENDING=0
  FAILED=0
  SKIPPED=0
  if [ -n "${BUCKETS}" ]; then
    TOTAL="$(printf '%s\n' "${BUCKETS}" | grep -c . || true)"
    PENDING="$(printf '%s\n' "${BUCKETS}" | grep -c '^pending$' || true)"
    FAILED="$(printf '%s\n' "${BUCKETS}" | grep -cE '^(fail|cancel)$' || true)"
    SKIPPED="$(printf '%s\n' "${BUCKETS}" | grep -c '^skipping$' || true)"
  fi

  NOW="$(date +%s)"
  if [ "${TOTAL}" -ne "${PREV_TOTAL}" ]; then
    STABLE_SINCE="${NOW}"
  fi

  if [ "${TOTAL}" -gt 0 ] && [ "${PENDING}" -eq 0 ] &&
    [ "${TOTAL}" -eq "${PREV_TOTAL}" ] && [ $((NOW - STABLE_SINCE)) -ge "${SETTLE}" ]; then
    break
  fi

  REPORT="${TOTAL} registered, ${PENDING} pending"
  if [ "${REPORT}" != "${PREV_REPORT}" ]; then
    say "watch-pr-checks: ${REPORT}"
    PREV_REPORT="${REPORT}"
  fi
  PREV_TOTAL="${TOTAL}"

  if [ "$(date +%s)" -ge "${DEADLINE}" ]; then
    report_timeout "checks to settle"
  fi
  if [ "${INTERVAL}" -gt 0 ]; then
    sleep "${INTERVAL}"
  fi
done

# --- 判定 ---

# 監視の間に新しい push があれば，見ていた結果は別 commit のものである
AFTER_OID="$(gh_head_oid)"
if [ -z "${AFTER_OID}" ]; then
  REASON=head_unavailable
  warn "error: could not re-read the head of PR #${PR} after watching ${EXPECT_SHA}"
  if [ -s "${LAST_ERR}" ]; then
    warn_file "${LAST_ERR}"
  fi
  exit 2
fi
if [ "${AFTER_OID}" != "${EXPECT_SHA}" ]; then
  REASON=head_changed
  warn "error: head moved to ${AFTER_OID} while watching ${EXPECT_SHA}"
  warn "error: rerun to watch the new commit"
  exit 2
fi

if [ "${FAILED}" -gt 0 ]; then
  REASON=checks_failed
  warn "error: ${FAILED} of ${TOTAL} checks did not pass on ${EXPECT_SHA}"
  exit 3
fi

# skip した check を通過件数へ数えない．「検査した」と「検査を飛ばした」は別である．
# すべて skip なら通過は 0 件である．これを「全 pass」と読ませると，
# path filter の設定ミスが green として沈黙する
REASON=settled
PASSED=$((TOTAL - SKIPPED))
if [ "${SKIPPED}" -eq 0 ]; then
  say "watch-pr-checks: all ${TOTAL} checks passed on ${EXPECT_SHA}"
elif [ "${PASSED}" -eq 0 ]; then
  say "watch-pr-checks: no checks ran on ${EXPECT_SHA} (${SKIPPED} skipped)"
else
  say "watch-pr-checks: all ${PASSED} checks passed on ${EXPECT_SHA} (${SKIPPED} skipped)"
fi
