#!/usr/bin/env bash
# PR のタイトル・本文・コミットメッセージに Claude Code のセッション URL が
# 含まれていないかを検査する．見つかれば ::error:: で場所を示し exit 1 で止める．
#
# 入力（環境変数）:
#   GH_TOKEN  - GitHub token（必須．pull-requests: read で足りる）
#   REPO      - owner/repo 形式のリポジトリ識別子（必須）
#   PR_NUMBER - PR 番号（必須）
#
# 終了コード:
#   0 - 検出なし
#   1 - 検出あり（blocking）
#   2 - API 取得失敗などの実行エラー（fail-closed．検査できない PR は通さない）
#
# 検出パターン（大文字小文字を区別しない）:
#   - claude.ai/code/session_… または claude.ai/code/cse_…（素の URL 形式）
#   - Claude-Session:（git trailer 形式）
#
# 背景: Claude Code は cloud / Remote Control セッションから作る commit と PR に
# 既定でセッション URL を付ける（attribution.sessionUrl，既定 true）．公開 repo の
# 履歴へ残ると commit 検索で横断的に集められる．発生源の設定と併せて
# docs/session-url-check.md を参照する．

set -uo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"

readonly PATTERN='claude\.ai/code/(session_|cse_)|Claude-Session:'

# 1 行 1 レコードへ平坦化する．先頭列は出所（pull-request か commit SHA）．
# 複数行の本文は行ごとに分け，検出行だけを報告できるようにする．
pr_lines="$(gh api "repos/${REPO}/pulls/${PR_NUMBER}" \
  --jq '([.title, (.body // "")] | join("\n") | split("\n")[]) | "pull-request\t" + .')" || {
  echo "::error::Failed to fetch pull request #${PR_NUMBER} of ${REPO}"
  exit 2
}

# shellcheck disable=SC2016 # $sha は jq の変数であり，シェル展開させないため単一引用符が意図
commit_lines="$(gh api --paginate "repos/${REPO}/pulls/${PR_NUMBER}/commits" \
  --jq '.[] | .sha as $sha | (.commit.message | split("\n")[]) | $sha + "\t" + .')" || {
  echo "::error::Failed to fetch commits of pull request #${PR_NUMBER} of ${REPO}"
  exit 2
}

# grep は非一致で exit 1，異常で exit 2 以上を返す．非一致だけを「検出なし」とし，
# 異常は API 失敗と同じく fail-closed で扱う．
grep_rc=0
findings="$(printf '%s\n%s\n' "${pr_lines}" "${commit_lines}" | grep -iE "${PATTERN}")" || grep_rc=$?
if [ "${grep_rc}" -gt 1 ]; then
  echo "::error::grep failed with exit ${grep_rc} while scanning PR #${PR_NUMBER}"
  exit 2
fi

if [ -z "${findings}" ]; then
  echo "No Claude session URL found in PR #${PR_NUMBER} (title, body, and commit messages)"
  exit 0
fi

count=0
while IFS=$'\t' read -r source text; do
  [ -n "${source}" ] || continue
  count=$((count + 1))
  echo "::error::Claude session URL found in ${source}: ${text}"
done <<<"${findings}"

echo "::error::${count} line(s) contain a Claude session URL. Remove them (amend or rebase the commits, edit the PR body) and set attribution.sessionUrl=false in Claude Code settings."
exit 1
