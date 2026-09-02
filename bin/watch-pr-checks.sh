#!/usr/bin/env bash

# PR の checks が出そろうまで監視する（Issue #133）．
#
# gh pr checks --watch を push 直後に実行すると，checks 未登録の時点で
# 「no checks reported」を返して即終了する．また gh 側の PR head 情報は
# push へ数十秒遅れることがあり，1 つ前の commit の run を掴んだまま
# 「全 pass」を返す（PR #159 の実例）．どちらも「CI green」の誤認を生む．
#
# --watch は完了までブロックし，中断の手立てを持たない．タイムアウトを
# 効かせるため，またワークフローごとに異なる登録の時刻を吸収するため，
# --watch は使わず自前で状態を polling する．
#
# 実行列:
#   1. head リポジトリの実体（git ls-remote）を監視対象 commit の正とする
#   2. gh pr view の headRefOid がその commit へ追いつくまで待つ
#   3. checks の状態を polling し，完了の 4 条件がそろうまで待つ．
#      1 件以上あること，pending が無いこと，件数が前回の照会から変わって
#      いないこと，件数が変わらなくなってから --settle 秒が過ぎたこと
#   4. head が動いていないことを確認する
#   5. fail・cancel の有無で終了コードを決める
#
# 終了コード:
#   0  監視対象 commit で全 checks が pass した
#   1  入力エラー・環境エラー
#   2  タイムアウト，または監視対象 commit の不一致
#   3  checks が pass しなかった

set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: watch-pr-checks.sh <pr-number> [--timeout SECONDS] [--interval SECONDS]
                          [--settle SECONDS] [--expect-sha SHA]

  pr-number      監視する PR の番号
  --timeout      監視全体のタイムアウト秒（既定: 600）．段ごとに取り直さない
  --interval     ポーリング間隔秒（既定: 10）
  --settle       件数が動かなくなってから完了と見なすまでの秒数（既定: 120）
  --expect-sha   監視対象 commit を明示する（40 桁）．origin への問い合わせを省く
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

# gh は push 直後に古い head を返すことがある．遅れない側であるリモートの
# 実体を正とし，gh の側をそこへ追いつかせる．
#
# fork からの PR では head ブランチが origin に無い．同名のブランチが base に
# あると，無関係な commit を掴んだまま待つ．head の所属先を解決してから引く
if [ -z "${EXPECT_SHA}" ]; then
  PR_INFO="$(gh pr view "${PR}" \
    --json headRefName,isCrossRepository,headRepositoryOwner,headRepository \
    --jq '[.headRefName, (.isCrossRepository | tostring), .headRepositoryOwner.login, .headRepository.name] | @tsv')"
  # IFS のタブは空白類のため read では連続を 1 つに詰め，空欄があると列がずれる．
  # cut は詰めないため列の位置が保たれる
  BRANCH="$(printf '%s' "${PR_INFO}" | cut -f1)"
  CROSS_REPO="$(printf '%s' "${PR_INFO}" | cut -f2)"
  HEAD_OWNER="$(printf '%s' "${PR_INFO}" | cut -f3)"
  HEAD_REPO="$(printf '%s' "${PR_INFO}" | cut -f4)"
  if [ -z "${BRANCH}" ]; then
    echo "error: could not resolve the head branch of PR #${PR}" >&2
    exit 1
  fi

  if [ "${CROSS_REPO}" = "true" ]; then
    if [ -z "${HEAD_OWNER}" ] || [ -z "${HEAD_REPO}" ]; then
      echo "error: could not resolve the head repository of PR #${PR}" >&2
      exit 1
    fi
    REMOTE="https://github.com/${HEAD_OWNER}/${HEAD_REPO}.git"
  else
    REMOTE="origin"
  fi

  EXPECT_SHA="$(git ls-remote "${REMOTE}" "refs/heads/${BRANCH}" | cut -f1)"
  if [ -z "${EXPECT_SHA}" ]; then
    echo "error: branch ${BRANCH} not found on ${REMOTE} (push it first)" >&2
    exit 1
  fi
  echo "watch-pr-checks: target commit ${EXPECT_SHA} (branch ${BRANCH} on ${REMOTE})"
else
  echo "watch-pr-checks: target commit ${EXPECT_SHA}"
fi

# --- 問い合わせ ---

# gh の失敗を「条件未成立」と区別できないまま待ち続けると，認証切れが
# 単なるタイムアウトに見える．最後の stderr を残してタイムアウト時に示す．
# 保持するのは「最後に観測した失敗」とする．後続の成功で消さない．
# 直後の 1 回が成功しただけで原因が消えると，追跡できないためである
LAST_ERR="$(mktemp)"
CALL_ERR="$(mktemp)"
trap 'rm -f "${LAST_ERR}" "${CALL_ERR}"' EXIT

keep_error() {
  if [ -s "${CALL_ERR}" ]; then
    cat "${CALL_ERR}" >"${LAST_ERR}"
  fi
}

gh_head_oid() {
  gh pr view "${PR}" --json headRefOid --jq .headRefOid 2>"${CALL_ERR}" || true
  keep_error
}

gh_head_matches() {
  [ "$(gh_head_oid)" = "${EXPECT_SHA}" ]
}

# pending・failure でも gh は結果を出しつつ非 0 で終える（pending は exit 8）．
# 終了コードで判定すると検査中の PR を照会失敗と誤読するため，出力だけを見る．
# 出力が無い状態は「未登録」と「照会失敗」の両方を含み，どちらも待機を続ける
checks_buckets() {
  gh pr checks "${PR}" --json name,state,bucket --jq '.[].bucket' 2>"${CALL_ERR}" || true
  keep_error
}

# --timeout は監視全体に掛かる．段ごとに取り直すと合計が 2 倍になりうるため，
# 締切は 1 度だけ決めて両方の待機で使い回す
DEADLINE=$(($(date +%s) + TIMEOUT))

report_timeout() {
  echo "error: timed out waiting for $1 (commit ${EXPECT_SHA})" >&2
  if [ -s "${LAST_ERR}" ]; then
    echo "error: last gh error was:" >&2
    cat "${LAST_ERR}" >&2
  fi
  exit 2
}

# --- gh がリモートへ追いつくのを待つ ---

echo "watch-pr-checks: waiting for gh to catch up with the remote"
while ! gh_head_matches; do
  if [ "$(date +%s)" -ge "${DEADLINE}" ]; then
    report_timeout "gh to report the target commit"
  fi
  if [ "${INTERVAL}" -gt 0 ]; then
    sleep "${INTERVAL}"
  fi
done

# --- checks が出そろうのを待つ ---

# 完了の条件は 4 つである．1 件以上あること，pending が無いこと，件数が前回の
# 照会から変わっていないこと，件数が変わらなくなってから --settle 秒が過ぎたこと．
# 後ろの 2 つは，登録の時刻が workflow ごとに異なるためである．
# 先に見えた check だけで「全 pass」と読む余地を消す．
#
# 待つ長さが要る．本リポジトリでは CodeRabbit の status が push 直後に付き，
# workflow の登録は約 1 分後だった．1 間隔だけの据え置きでは，前者だけを見て
# 「1 件が全 pass」と報告してしまう（2026-09-02 に本スクリプトで実際に発生）．
# 既定の 120 秒は観測した遅延の 2 倍である．等倍では余裕が無い．
#
# それでも --settle より後に現れる check は追えない．そこまで要るなら
# GitHub 側の required checks 設定で担保する（本リポジトリは未設定）
echo "watch-pr-checks: waiting for checks to settle"
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
    echo "watch-pr-checks: ${REPORT}"
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
  echo "error: could not re-read the head of PR #${PR} after watching ${EXPECT_SHA}" >&2
  if [ -s "${LAST_ERR}" ]; then
    cat "${LAST_ERR}" >&2
  fi
  exit 2
fi
if [ "${AFTER_OID}" != "${EXPECT_SHA}" ]; then
  echo "error: head moved to ${AFTER_OID} while watching ${EXPECT_SHA}" >&2
  echo "error: rerun to watch the new commit" >&2
  exit 2
fi

if [ "${FAILED}" -gt 0 ]; then
  echo "error: ${FAILED} of ${TOTAL} checks did not pass on ${EXPECT_SHA}" >&2
  exit 3
fi

# skip した check を pass と混ぜない．「検査した」と「検査を飛ばした」は別である
if [ "${SKIPPED}" -gt 0 ]; then
  echo "watch-pr-checks: all ${TOTAL} checks passed on ${EXPECT_SHA} (${SKIPPED} skipped)"
else
  echo "watch-pr-checks: all ${TOTAL} checks passed on ${EXPECT_SHA}"
fi
