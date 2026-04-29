#!/usr/bin/env bash
# PR に 👀 reaction を付与する．composite action から最初の step として呼ばれ，
# 「workflow は起動済みで，これから lint review を行う」状態を caller 側で即座に
# 判別できるようにするための UX nicety．
#
# 入力（環境変数）:
#   GH_TOKEN  - GitHub token（必須）
#   REPO      - owner/repo 形式のリポジトリ識別子（必須）
#   PR_NUMBER - PR 番号（必須）
#
# 仕様:
#   - GitHub Reactions API は同一 user × 同一 content の reaction を idempotent に
#     扱う（200/201）．連続実行や rerun でも reaction が重複生成されない．冪等な
#     ため curl の retry も安全．
#   - --retry 2 / --max-time 10 で「失敗しても review 本体は続行」方針との整合
#     を取る．--retry-all-errors は connection refused 等の非 5xx も retry 対象
#     に含める（curl 7.71+）．
#   - レスポンス保存先は mktemp で衝突回避し trap で削除．self-hosted runner や
#     act での並列実行・連続実行を想定．
#   - 必須 env が欠けている場合は execution error として非 0 終了．それ以外は
#     fail-open で常に exit 0．非 2xx は ::warning:: annotation で可視化する．

set -uo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"

REACTION_RESP="$(mktemp)"
trap 'rm -f "${REACTION_RESP}"' EXIT

HTTP_STATUS="$(
  curl -sS --retry 2 --retry-all-errors --max-time 10 \
    -o "${REACTION_RESP}" -w '%{http_code}' \
    -X POST \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO}/issues/${PR_NUMBER}/reactions" \
    -d '{"content":"eyes"}'
)" || HTTP_STATUS="curl-error"

if [[ "${HTTP_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
  echo "Added 👀 reaction to PR #${PR_NUMBER} (HTTP ${HTTP_STATUS})"
else
  echo "::warning::Failed to add 👀 reaction (HTTP ${HTTP_STATUS}); continuing review"
  [ -f "${REACTION_RESP}" ] && cat "${REACTION_RESP}" || true
fi
