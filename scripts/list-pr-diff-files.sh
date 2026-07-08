#!/usr/bin/env bash
# PR の差分ファイル一覧（filename）を 1 行 1 ファイルで stdout に出す．
# lint summary（scripts/count-lint-findings.py の --diff-files-from）を
# PR 差分ファイルのみに絞り込むための入力を作る（Issue #59）．
#
# 入力（環境変数）:
#   GH_TOKEN  - GitHub token（必須）
#   REPO      - owner/repo 形式のリポジトリ識別子（必須）
#   PR_NUMBER - PR 番号（必須）
#
# 仕様:
#   - GET /repos/:owner/:repo/pulls/:pr/files?per_page=100 を叩き，
#     各要素の filename を stdout へ 1 行ずつ出す
#   - Link ヘッダの rel="next" を辿り全ページを結合する（post-lint-summary.sh
#     の pagination 実装と同じ方式）
#   - 必須 env 不足は execution error として非 0 終了
#   - GET 失敗（非 2xx）時は ::warning:: を出し非 0 終了する．呼び出し側
#     （composite action）はこれを見て --diff-files-from を渡すのを諦め，
#     従来どおりリポジトリ全体スコープにフォールバックする．「取得失敗」を
#     「差分ファイル 0 件」として誤解釈させない（0 件のまま渡すと summary が
#     全指摘を隠してしまう）ための fail-open 設計

set -uo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"

GET_RESP="$(mktemp)"
GET_HEADERS="$(mktemp)"
trap 'rm -f "${GET_RESP}" "${GET_HEADERS}"' EXIT

URL="https://api.github.com/repos/${REPO}/pulls/${PR_NUMBER}/files?per_page=100"
while [ -n "${URL}" ]; do
  : > "${GET_RESP}"
  : > "${GET_HEADERS}"
  GET_STATUS="$(
    curl -sS --retry 2 --retry-all-errors --max-time 10 \
      -o "${GET_RESP}" -D "${GET_HEADERS}" -w '%{http_code}' \
      -H "Authorization: Bearer ${GH_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -X GET "${URL}"
  )" || GET_STATUS="curl-error"

  if ! [[ "${GET_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
    echo "::warning::Failed to list PR diff files (HTTP ${GET_STATUS})" >&2
    [ -f "${GET_RESP}" ] && cat "${GET_RESP}" >&2 || true
    exit 1
  fi

  # `set -e` を使わない設計のため，JSON parse 失敗等の異常終了を明示的に
  # 検知して非 0 で終わらせる．検知しないと「差分ファイル 0 件」と誤認され，
  # 全指摘が summary から静かに消えるサイレント不具合になる．
  python3 - "${GET_RESP}" <<'PY' || exit 1
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    payload = json.load(f)
for item in payload:
    filename = item.get("filename")
    if filename:
        print(filename)
PY

  # Link ヘッダから rel="next" の URL を抽出する（post-lint-summary.sh と同じ実装）．
  # `set -o pipefail` 下では次ページが無い（grep 不一致）とき pipeline の
  # 終了コードが非 0 になり，ループ最後の代入がそのままスクリプト自身の
  # 終了コードを汚染する．`|| true` で意図的に握りつぶす．
  URL="$( (grep -i '^link:' "${GET_HEADERS}" \
    | sed -nE 's/.*<([^>]*)>;[[:space:]]*rel=["'"'"']next["'"'"'].*/\1/p' \
    | head -n1) || true )"
done

exit 0
