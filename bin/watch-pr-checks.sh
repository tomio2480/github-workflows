#!/usr/bin/env bash

# PR の checks が登録されるのを待ってから監視する（Issue #133）．
#
# gh pr checks --watch を push 直後に実行すると，checks 未登録の時点で
# 「no checks reported」を返して即終了する．また gh 側の PR head 情報は
# push へ数十秒遅れることがあり，1 つ前の commit の run を掴んだまま
# 「全 pass」を返す（PR #159 の実例）．どちらも「CI green」の誤認を生む．
#
# 実行列:
#   1. origin の実体（git ls-remote）を監視対象 commit の正とする
#   2. gh pr view の headRefOid がその commit へ追いつくまで待つ
#   3. checks が 1 件以上登録されるまで待つ
#   4. gh pr checks --watch へ移行する．完了時に件数が増えていれば watch し直す
#   5. watch 完了後に head が動いていないことを確認する
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
                          [--expect-sha SHA]

  pr-number      監視する PR の番号
  --timeout      各待機段のタイムアウト秒（既定: 600）
  --interval     ポーリング間隔秒（既定: 10）
  --expect-sha   監視対象 commit を明示する（40 桁）．origin への問い合わせを省く
USAGE
  exit 1
}

PR="${1:-}"
[ $# -ge 1 ] || usage
shift

TIMEOUT=600
INTERVAL=10
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

if [ -n "${EXPECT_SHA}" ] && ! [[ "${EXPECT_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: --expect-sha must be a full 40-hex SHA: ${EXPECT_SHA}" >&2
  exit 1
fi

# --- 監視対象 commit の確定 ---

# gh は push 直後に古い head を返すことがある．遅れない側である origin の
# 実体を正とし，gh の側をそこへ追いつかせる
if [ -z "${EXPECT_SHA}" ]; then
  BRANCH="$(gh pr view "${PR}" --json headRefName --jq .headRefName)"
  if [ -z "${BRANCH}" ]; then
    echo "error: could not resolve the head branch of PR #${PR}" >&2
    exit 1
  fi
  EXPECT_SHA="$(git ls-remote origin "refs/heads/${BRANCH}" | cut -f1)"
  if [ -z "${EXPECT_SHA}" ]; then
    echo "error: branch ${BRANCH} not found on origin (push it first)" >&2
    exit 1
  fi
  echo "watch-pr-checks: target commit ${EXPECT_SHA} (branch ${BRANCH})"
else
  echo "watch-pr-checks: target commit ${EXPECT_SHA}"
fi

# --- 待機 ---

# gh の失敗を「条件未成立」と区別できないまま待ち続けると，認証切れが
# 単なるタイムアウトに見える．最後の stderr を残してタイムアウト時に示す
LAST_ERR="$(mktemp)"
trap 'rm -f "${LAST_ERR}"' EXIT

wait_until() {
  local desc="$1"
  shift
  local deadline
  deadline=$(($(date +%s) + TIMEOUT))
  while :; do
    if "$@"; then
      return 0
    fi
    if [ "$(date +%s)" -ge "${deadline}" ]; then
      echo "error: timed out waiting for ${desc} (commit ${EXPECT_SHA})" >&2
      if [ -s "${LAST_ERR}" ]; then
        echo "error: last gh error was:" >&2
        cat "${LAST_ERR}" >&2
      fi
      exit 2
    fi
    if [ "${INTERVAL}" -gt 0 ]; then
      sleep "${INTERVAL}"
    fi
  done
}

gh_head_oid() {
  gh pr view "${PR}" --json headRefOid --jq .headRefOid 2>"${LAST_ERR}" || true
}

gh_head_matches() {
  [ "$(gh_head_oid)" = "${EXPECT_SHA}" ]
}

checks_count() {
  local out
  # pending・failure でも gh は件数を出しつつ非 0 で終える（pending は exit 8）．
  # 終了コードで判定すると検査中の PR を照会失敗と誤読するため，出力だけを見る
  out="$(gh pr checks "${PR}" --json name,state --jq length 2>"${LAST_ERR}" || true)"
  if [[ "${out}" =~ ^[0-9]+$ ]]; then
    echo "${out}"
  else
    # 数値以外（照会失敗・空）は 0 件として扱い，未登録と同じ経路へ落とす
    echo 0
  fi
}

checks_registered() {
  [ "$(checks_count)" -gt 0 ]
}

echo "watch-pr-checks: waiting for gh to catch up with origin"
wait_until "gh to report the target commit" gh_head_matches

echo "watch-pr-checks: waiting for checks to be registered"
wait_until "checks to be registered" checks_registered

# --- 監視 ---

# workflow ごとに登録の時刻が異なるため，先に見えていた check だけで watch が
# 完了しうる．件数が増えていれば，遅れて現れた check を含めて watch し直す．
# 最後の照会より後に現れる check までは追えない．そこまで要るなら
# GitHub 側の required checks 設定で担保する
WATCH_DEADLINE=$(($(date +%s) + TIMEOUT))
WATCH_STATUS=0
while :; do
  COUNT_BEFORE="$(checks_count)"
  WATCH_STATUS=0
  gh pr checks "${PR}" --watch || WATCH_STATUS=$?
  COUNT_AFTER="$(checks_count)"
  if [ "${COUNT_AFTER}" -le "${COUNT_BEFORE}" ]; then
    break
  fi
  echo "watch-pr-checks: checks grew from ${COUNT_BEFORE} to ${COUNT_AFTER}; watching again"
  if [ "$(date +%s)" -ge "${WATCH_DEADLINE}" ]; then
    echo "error: checks kept appearing until the timeout (commit ${EXPECT_SHA})" >&2
    exit 2
  fi
done

# watch 中に新しい push があれば，結果は別 commit のものである
AFTER_OID="$(gh_head_oid)"
if [ "${AFTER_OID}" != "${EXPECT_SHA}" ]; then
  echo "error: head moved to ${AFTER_OID} while watching ${EXPECT_SHA}" >&2
  echo "error: rerun to watch the new commit" >&2
  exit 2
fi

if [ "${WATCH_STATUS}" -ne 0 ]; then
  echo "error: checks did not pass on ${EXPECT_SHA} (gh exit ${WATCH_STATUS})" >&2
  exit 3
fi

echo "watch-pr-checks: all checks passed on ${EXPECT_SHA}"
