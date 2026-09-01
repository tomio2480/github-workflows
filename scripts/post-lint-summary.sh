#!/usr/bin/env bash
# PR に lint の summary コメントを upsert する．composite action の最終 step
# として呼ばれ，markdownlint / textlint の件数を一覧表示する．
#
# reviewdog の github-pr-review reporter は findings ゼロのとき何も投稿しない
# ため，PR を見たユーザーが「lint が走ったが指摘がなかった」 のか「workflow
# が起動していない」 のか区別できない．本スクリプトはこの UX 欠落を補う．
#
# 入力（環境変数）:
#   GH_TOKEN     - GitHub token（必須）
#   REPO         - owner/repo 形式のリポジトリ識別子（必須）
#   PR_NUMBER    - PR 番号（必須）
#   SUMMARY_JSON - count-lint-findings.py が出した JSON ファイルのパス（必須）
#   LINT_BASE_SHA / LINT_HEAD_SHA - 検査対象コミットの併記用（任意）．
#     両方揃ったときだけ本文へ「検査対象」行を出す（Issue #119）．
#     PR の lint はマージコミット（head を base へ merge した木）を checkout
#     して走るため，「リポジトリ全体」の件数は main の現在値ではなく
#     その時点の base に対する値である．どの base を数えたかを summary に
#     残すことで，解消済みの件数が古い base のせいで残って見えるケースを
#     summary 単体で判別できるようにする．
#   LINT_REPORT_ARTIFACT - lint レポートをまとめた artifact 名（任意）．
#     渡されたときは「リポジトリ全体の内訳はこの artifact から取れる」と案内し，
#     空・未設定のときは取得できない旨と有効化手段を案内する（Issue #148）．
#   LINT_REPORT_FILES - artifact に実際に入ったレポートのファイル名（任意）．
#     カンマ区切り．未設定なら markdownlint / textlint 両方が入っている前提で
#     案内する．片方の lint が skip された run では実態と食い違うため，
#     composite action 側が存在するファイルだけを渡す．
#
# 仕様:
#   - hidden marker `<!-- gh-workflows-lint-summary -->` 付きコメントを GET で
#     検索し，存在すれば PATCH，無ければ POST する（upsert）
#   - SUMMARY_JSON の diff_scoped が true のとき，表に「リポジトリ全体」列を
#     併記する（Issue #104）．旧スキーマの payload は従来表示のまま
#   - 必須 env 不足は execution error として非 0 終了
#   - GET / POST / PATCH 失敗時は ::warning:: で annotation 化し exit 0
#     （fail-open．reviewdog 本体は既に投稿済みのため UX nicety で job を
#     落とさない方針）

# `-e` は付けない．非 2xx 応答は ::warning:: + exit 0 で fail-open する設計の
# ため，個別の HTTP エラーパスを明示的に書き分ける．`-u` で未定義変数早期検出，
# `-o pipefail` で pipe 中の途中失敗を捕捉する．
set -uo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${PR_NUMBER:?PR_NUMBER is required}"
: "${SUMMARY_JSON:?SUMMARY_JSON is required}"

MARKER='<!-- gh-workflows-lint-summary -->'

BODY_FILE="$(mktemp)"
PAYLOAD_FILE="$(mktemp)"
GET_RESP="$(mktemp)"
GET_HEADERS="$(mktemp)"
WRITE_RESP="$(mktemp)"
trap 'rm -f "${BODY_FILE}" "${PAYLOAD_FILE}" "${GET_RESP}" "${GET_HEADERS}" "${WRITE_RESP}"' EXIT

# Render comment body from summary JSON．
# 出力先をファイルパスで明示渡しすることで stdout の encoding 依存（Windows
# 環境の cp932 等）を避け，UTF-8 で確実に書き出す．Actions run へのリンクと
# findings 上位の <details> 一覧を含めることで，reviewdog の filter-mode に
# よって inline 化されない指摘でも PR コメントから辿れるようにする．
python3 - "${SUMMARY_JSON}" "${BODY_FILE}" <<'PY'
import json
import os
import sys

MAX_FINDINGS_PER_TOOL = 20

with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)

md = data.get("markdownlint", {})
md_total = int(md.get("total", 0))
md_findings = md.get("findings", []) or []

tx = data.get("textlint", {})
tx_total = int(tx.get("total", 0))
tx_findings = tx.get("findings", []) or []

# Issue #104: diff_scoped のとき，diff 絞り込み前のリポジトリ全体件数を併記する．
# 旧スキーマ（diff_scoped / repo_total なし）の payload では従来表示に落とす．
diff_scoped = bool(data.get("diff_scoped", False))
md_repo_total = int(md.get("repo_total", md_total))
tx_repo_total = int(tx.get("repo_total", tx_total))

text_cell = str(tx_total)
if tx_total > 0:
    parts = []
    for label in ("error", "warning", "info"):
        n = int(tx.get(label, 0))
        if n:
            parts.append(f"{label}: {n}")
    if parts:
        text_cell = f"{tx_total} ({' / '.join(parts)})"

server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
repo = os.environ.get("GITHUB_REPOSITORY", "")
run_id = os.environ.get("GITHUB_RUN_ID", "")
run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
workspace = (os.environ.get("GITHUB_WORKSPACE") or "").rstrip("/")
run_url = ""
if repo and run_id:
    run_url = f"{server}/{repo}/actions/runs/{run_id}"
    if run_attempt:
        run_url += f"/attempts/{run_attempt}"


def normalize_file(path: str) -> str:
    """runner 上の絶対パスを caller リポジトリ起点の相対パスに整える．

    GitHub Actions では `GITHUB_WORKSPACE` が caller チェックアウトのルート
    （例 `/home/runner/work/<repo>/<repo>`）として渡るため，それを strip する．
    workspace 配下に該当しない path はそのまま返す．
    """
    if workspace and path.startswith(workspace + "/"):
        return path[len(workspace) + 1:]
    return path


def normalize_rule(rule: str) -> str:
    """textlint checkstyle が付ける `eslint.rules.` プレフィックスを取り除く．

    textlint v14 の checkstyle formatter は `source` 属性を `eslint.rules.<rule>`
    で出すが，summary 上では冗長になるため表示専用に剥がす．JSON（集計層）の
    生データは触らず，rendering 層で正規化する責務分離を保つ．
    """
    prefix = "eslint.rules."
    return rule[len(prefix):] if rule.startswith(prefix) else rule


def render_findings(label, findings):
    if not findings:
        return []
    out = [
        "",
        f"<details><summary>{label} の指摘 {len(findings)} 件</summary>",
        "",
    ]
    shown = findings[:MAX_FINDINGS_PER_TOOL]
    for f in shown:
        file_ = normalize_file(f.get("file") or "?")
        line = f.get("line") or 0
        rule = normalize_rule(f.get("rule") or "")
        # message 内の改行は list の改行として解釈され 1 件分の表示が崩れる．
        # 半角スペースに置換して 1 行に畳む．`|` は将来テーブル併用したときの
        # 防衛のためエスケープしておく．
        msg = (
            (f.get("message") or "")
            .replace("\r\n", " ")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("|", "\\|")
        )
        sev = f.get("severity")
        sev_tag = f"[{sev}] " if sev else ""
        out.append(f"- `{file_}:{line}` {sev_tag}{rule}: {msg}")
    extra = len(findings) - len(shown)
    if extra > 0:
        out.append(f"- ...他 {extra} 件")
    out.append("")
    out.append("</details>")
    return out


lines = [
    "<!-- gh-workflows-lint-summary -->",
    "### Lint summary",
    "",
]
if diff_scoped:
    lines += [
        "| ツール | この PR の差分 | リポジトリ全体 |",
        "|---|---|---|",
        f"| markdownlint | {md_total} | {md_repo_total} |",
        f"| textlint | {text_cell} | {tx_repo_total} |",
        "",
    ]
else:
    lines += [
        "| ツール | 指摘 |",
        "|---|---|",
        f"| markdownlint | {md_total} |",
        f"| textlint | {text_cell} |",
        "",
    ]

# Issue #119: どのコミットを検査したかを 1 行併記する．全体件数は checkout
# した木（PR のマージコミット）の base 時点の値であり，main の現在値と
# 取り違えられやすいため，base を明示して summary 単体で判別可能にする．
base_sha = os.environ.get("LINT_BASE_SHA", "")
head_sha = os.environ.get("LINT_HEAD_SHA", "")
if base_sha and head_sha:
    lines += [
        f"検査対象: `Merge {head_sha[:7]} into {base_sha[:7]}`"
        f"（base: `{base_sha[:7]}`）",
        "",
    ]

# Issue #148: リポジトリ全体の内訳をどこで得られるかを案内する．個別の指摘は
# reviewdog へ流れるだけで Actions ログには残らないため，従来の「Actions ログ
# から確認」は誤案内だった．artifact 名が渡っていればそれを案内し，渡って
# いなければ取得できない旨と有効化の手段を明示する．
report_artifact = os.environ.get("LINT_REPORT_ARTIFACT", "")
# diff 絞り込みのない payload では「リポジトリ全体」という対比が成り立たない．
# 表の見出しと同じ語彙で案内するため，主語を切り替える．
detail_subject = "リポジトリ全体の内訳" if diff_scoped else "指摘の全件"
if report_artifact:
    # 実際に artifact へ入ったレポートだけを案内する．fail-on-error: true の
    # caller では markdownlint の非ゼロ終了で textlint step が skip され，
    # 片方のレポートしか存在しないことがあるため（PR #152 のレビュー指摘）．
    report_files = [
        name.strip()
        for name in os.environ.get("LINT_REPORT_FILES", "").split(",")
        if name.strip()
    ] or ["markdownlint-report.txt", "textlint-report.xml"]
    joined_files = " と ".join(f"`{name}`" for name in report_files)
    repo_detail_hint = (
        f"{detail_subject}は Actions run の artifact `{report_artifact}` "
        f"にある {joined_files} から確認できます．"
    )
else:
    repo_detail_hint = (
        f"{detail_subject}はこのコメントからは取得できません．"
        "action の `upload-reports` input を `true` にすると，"
        "lint レポートが run の artifact として添付されます．"
    )

if md_total == 0 and tx_total == 0:
    if diff_scoped and (md_repo_total + tx_repo_total) > 0:
        lines.append(
            "この PR の差分に指摘はありません．"
            "リポジトリ全体には既存の指摘が残っています．" + repo_detail_hint
        )
    else:
        lines.append("指摘はありません．")
else:
    lines.append(
        "差分行に該当する指摘は inline コメントとして該当行に付きます．"
        "filter-mode（既定 `added`）の都合で inline 化されない指摘は"
        "下の details 一覧から確認してください．" + repo_detail_hint
    )
    lines += render_findings("markdownlint", md_findings)
    lines += render_findings("textlint", tx_findings)

if run_url:
    lines += ["", f"Actions run: {run_url}"]

with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
PY

# Wrap rendered body into a {"body": ...} JSON payload．
python3 - "${BODY_FILE}" "${PAYLOAD_FILE}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    body = f.read()
with open(sys.argv[2], "w", encoding="utf-8", newline="\n") as f:
    json.dump({"body": body}, f, ensure_ascii=False)
PY

# Locate existing comment with the marker (paginate via Link header)．
COMMENT_ID=""
URL="https://api.github.com/repos/${REPO}/issues/${PR_NUMBER}/comments?per_page=100"
while [ -n "${URL}" ]; do
  : >"${GET_RESP}"
  : >"${GET_HEADERS}"
  GET_STATUS="$(
    curl -sS --retry 2 --retry-all-errors --max-time 10 \
      -o "${GET_RESP}" -D "${GET_HEADERS}" -w '%{http_code}' \
      -H "Authorization: Bearer ${GH_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -X GET "${URL}"
  )" || GET_STATUS="curl-error"

  if ! [[ "${GET_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
    echo "::warning::Failed to list PR comments (HTTP ${GET_STATUS}); skipping summary"
    [ -f "${GET_RESP}" ] && cat "${GET_RESP}" || true
    exit 0
  fi

  COMMENT_ID="$(
    python3 - "${GET_RESP}" "${MARKER}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as f:
    payload = json.load(f)
marker = sys.argv[2]
for comment in payload:
    if marker in (comment.get("body") or ""):
        print(comment["id"])
        break
PY
  )"

  if [ -n "${COMMENT_ID}" ]; then
    break
  fi

  # Link ヘッダから rel="next" の URL を抽出する．rel 属性の引用符種別
  # （単一・二重）と前後空白の揺れを許容するため，[[:space:]]* と
  # [\"'] を使う．GitHub API は通常二重引用符・空白 1 個で返すが，
  # プロキシや将来の仕様変更による揺れに備える．
  URL="$(grep -i '^link:' "${GET_HEADERS}" |
    sed -nE 's/.*<([^>]*)>;[[:space:]]*rel=["'"'"']next["'"'"'].*/\1/p' |
    head -n1)"
done

if [ -n "${COMMENT_ID}" ]; then
  METHOD="PATCH"
  TARGET="https://api.github.com/repos/${REPO}/issues/comments/${COMMENT_ID}"
else
  METHOD="POST"
  TARGET="https://api.github.com/repos/${REPO}/issues/${PR_NUMBER}/comments"
fi

WRITE_STATUS="$(
  curl -sS --retry 2 --retry-all-errors --max-time 10 \
    -o "${WRITE_RESP}" -w '%{http_code}' \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    -X "${METHOD}" "${TARGET}" \
    --data-binary "@${PAYLOAD_FILE}"
)" || WRITE_STATUS="curl-error"

if [[ "${WRITE_STATUS}" =~ ^2[0-9][0-9]$ ]]; then
  echo "${METHOD} lint summary comment to PR #${PR_NUMBER} (HTTP ${WRITE_STATUS})"
else
  echo "::warning::Failed to ${METHOD} lint summary comment (HTTP ${WRITE_STATUS}); continuing"
  [ -f "${WRITE_RESP}" ] && cat "${WRITE_RESP}" || true
fi
