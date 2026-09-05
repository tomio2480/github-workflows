#!/usr/bin/env bats

# bin/lint-md.sh integration tests.
#
# Spec:
#   Arguments:
#     --all               対象を追跡済み Markdown 全件にする
#     --base <ref>        差分の基点を明示する
#     --glob <pattern>    lint 対象の glob（既定 **/*.md）
#     --ignore-glob <pat> 報告から除外する path glob
#     <files...>          対象を明示する（指定時は差分選定を行わない）
#   Environment:
#     LINT_MD_CACHE_DIR - lint 依存キャッシュの置き場所
#   Behavior:
#     - 呼び出し元リポジトリ（PWD）を caller として中央 templates の設定で lint する
#     - lint は composite action と同じく glob 全体へ掛ける
#     - 報告は対象ファイルへ絞る．対象外の指摘では失敗させない
#     - 対象が 0 件なら lint を起動せず 0 終了する
#     - 指摘があれば 1 で終了する（CI の reviewdog と異なりローカルはブロックする）
#     - lint の実行失敗（2）と指摘あり（1）を区別する
#     - 生成した runtime config を作業ツリーへ残さない
#     - lint は LF 正規化した複製へ掛け，作業ツリーの改行は書き換えない
#     - 報告のパスを元へ戻せないときは 0 終了せず実行失敗とする
#
# Test strategy:
#   npm と lint バイナリを差し替え，ネットワークと実 lint を排除する．
#   中央設定の解決・runtime 生成・集計・絞り込みは実物を動かす．

setup() {
  CENTRAL_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${CENTRAL_ROOT}/bin/lint-md.sh"

  export GIT_AUTHOR_NAME="test"
  export GIT_AUTHOR_EMAIL="test@example.com"
  export GIT_COMMITTER_NAME="test"
  export GIT_COMMITTER_EMAIL="test@example.com"

  export FAKE_LOG_DIR="${BATS_TEST_TMPDIR}/log"
  FAKE_BIN="${BATS_TEST_TMPDIR}/bin"
  FAKE_LINT_BIN="${BATS_TEST_TMPDIR}/lintbin"
  mkdir -p "${FAKE_LOG_DIR}" "${FAKE_BIN}" "${FAKE_LINT_BIN}"

  # 指摘を出すファイルは FAKE_FINDING_PATH で指定する（既定は new.md）．
  cat > "${FAKE_LINT_BIN}/markdownlint-cli2" <<'FAKE'
#!/usr/bin/env bash
# 実行失敗は banner を出さずに終わる．指摘ありの exit 1 と区別される．
if [ -n "${FAKE_MDLINT_EXEC_ERROR:-}" ]; then
  echo "cannot load config" >&2
  exit 1
fi
echo "markdownlint-cli2 v0.0.0-fake"
printf '%s\n' "$@" > "${FAKE_LOG_DIR}/mdlint-args"
pwd > "${FAKE_LOG_DIR}/mdlint-cwd"
if [ -n "${FAKE_INSPECT_FILE:-}" ] && [ -f "${FAKE_INSPECT_FILE}" ]; then
  tr -dc '\r' < "${FAKE_INSPECT_FILE}" | wc -c > "${FAKE_LOG_DIR}/mdlint-cr"
fi
if [ -n "${FAKE_MDLINT_FINDINGS:-}" ]; then
  echo "${FAKE_FINDING_PATH:-new.md}:1 MD000/fake fake mdlint finding"
  echo "Summary: 1 error(s)"
  exit 1
fi
echo "Summary: 0 error(s)"
exit 0
FAKE

  cat > "${FAKE_LINT_BIN}/textlint" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$@" > "${FAKE_LOG_DIR}/textlint-args"
pwd > "${FAKE_LOG_DIR}/textlint-cwd"
# linter が実際に読むファイルの CR 数を残す．正規化の有無をここで見る．
if [ -n "${FAKE_INSPECT_FILE:-}" ] && [ -f "${FAKE_INSPECT_FILE}" ]; then
  tr -dc '\r' < "${FAKE_INSPECT_FILE}" | wc -c > "${FAKE_LOG_DIR}/textlint-cr"
fi
if [ -n "${FAKE_TEXTLINT_EXEC_ERROR:-}" ]; then
  echo "cannot resolve rule" >&2
  exit 1
fi
if [ -n "${FAKE_TEXTLINT_FINDINGS:-}" ]; then
  # 実物の textlint は checkstyle 出力へ絶対パスを書く．Git Bash では
  # C:\... 形式になるため，同じ形を作って集計側の相対化を検証する．
  FINDING_FILE="${FAKE_FINDING_PATH:-new.md}"
  if [ -n "${FAKE_TEXTLINT_ABSOLUTE:-}" ]; then
    FINDING_FILE="$(pwd -W 2>/dev/null || pwd)/${FINDING_FILE}"
  fi
  # workspace prefix を剥がせない絶対パス．集計では黙って捨てられる．
  if [ -n "${FAKE_TEXTLINT_UNMAPPED:-}" ]; then
    FINDING_FILE="/elsewhere/${FAKE_FINDING_PATH:-new.md}"
  fi
  cat <<XML
<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
<file name="${FINDING_FILE}">
<error line="1" column="1" severity="error" message="fake textlint finding" source="fake-rule" />
</file>
</checkstyle>
XML
  exit 1
fi
echo '<?xml version="1.0" encoding="UTF-8"?><checkstyle version="4.3"></checkstyle>'
exit 0
FAKE
  chmod +x "${FAKE_LINT_BIN}/markdownlint-cli2" "${FAKE_LINT_BIN}/textlint"

  # npm ci は node_modules/.bin へ偽の lint バイナリを置くだけにする．
  cat > "${FAKE_BIN}/npm" <<'FAKE'
#!/usr/bin/env bash
if [ "$1" = "ci" ]; then
  mkdir -p "./node_modules/.bin"
  cp "${FAKE_LINT_BIN}"/* "./node_modules/.bin/"
fi
exit 0
FAKE
  chmod +x "${FAKE_BIN}/npm"
  export FAKE_LINT_BIN
  PATH="${FAKE_BIN}:${PATH}"
  export PATH

  export LINT_MD_CACHE_DIR="${BATS_TEST_TMPDIR}/cache"

  WORK="${BATS_TEST_TMPDIR}/work"
  mkdir -p "${WORK}"
  cd "${WORK}"
  git init -q -b main .
  git config core.autocrlf false
  echo "# sample" > sample.md
  git add -A
  git commit -q -m "initial"
}

teardown() {
  unset FAKE_MDLINT_FINDINGS FAKE_TEXTLINT_FINDINGS FAKE_TEXTLINT_EXEC_ERROR \
    FAKE_FINDING_PATH FAKE_TEXTLINT_ABSOLUTE BASH_ENV FAKE_MDLINT_EXEC_ERROR \
    FAKE_INSPECT_FILE FAKE_TEXTLINT_UNMAPPED
}

@test "exits 0 without running lint when nothing changed" {
  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ ! -f "${FAKE_LOG_DIR}/mdlint-args" ]
  [ ! -f "${FAKE_LOG_DIR}/textlint-args" ]
}

@test "runs both linters over the glob and exits 0 when clean" {
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -qxF -- "**/*.md" "${FAKE_LOG_DIR}/mdlint-args"
  grep -qxF -- "**/*.md" "${FAKE_LOG_DIR}/textlint-args"
  [[ "${output}" == *"指摘なし"* ]]
}

@test "passes the central markdownlint config to markdownlint-cli2" {
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -qx -- "--config" "${FAKE_LOG_DIR}/mdlint-args"
  grep -q "markdownlint-cli2.yaml$" "${FAKE_LOG_DIR}/mdlint-args"
}

@test "passes a generated runtime textlint config and the ignore path" {
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  grep -q "textlintrc.runtime.json$" "${FAKE_LOG_DIR}/textlint-args"
  grep -qx -- "--ignore-path" "${FAKE_LOG_DIR}/textlint-args"
  grep -qx -- "-f" "${FAKE_LOG_DIR}/textlint-args"
  grep -qx -- "checkstyle" "${FAKE_LOG_DIR}/textlint-args"
}

@test "prefers the caller config over the central template" {
  echo "# new" > new.md
  echo "config: {}" > .markdownlint-cli2.yaml

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  # caller 設定は絶対パスで渡る．linter は LF 正規化した複製の側で動くため，
  # リポジトリルート相対のままでは解決できない（Issue #169）．
  grep -q "/\.markdownlint-cli2\.yaml$" "${FAKE_LOG_DIR}/mdlint-args"
  ! grep -q "templates/.markdownlint-cli2.yaml" "${FAKE_LOG_DIR}/mdlint-args"
}

@test "honours an explicit --glob" {
  echo "# new" > new.md

  run bash "${SCRIPT}" --glob "docs/**/*.md"

  [ "${status}" -eq 0 ]
  grep -qxF -- "docs/**/*.md" "${FAKE_LOG_DIR}/mdlint-args"
}

@test "exits 1 when markdownlint reports a finding in a target file" {
  echo "# new" > new.md
  export FAKE_MDLINT_FINDINGS=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "exits 1 when textlint reports a finding in a target file" {
  echo "# new" > new.md
  export FAKE_TEXTLINT_FINDINGS=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake textlint finding"* ]]
}

@test "scopes textlint findings written with an absolute path" {
  echo "# new" > new.md
  export FAKE_TEXTLINT_FINDINGS=1
  export FAKE_TEXTLINT_ABSOLUTE=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake textlint finding"* ]]
}

@test "ignores absolute-path findings outside the target set" {
  echo "# new" > new.md
  export FAKE_TEXTLINT_FINDINGS=1
  export FAKE_TEXTLINT_ABSOLUTE=1
  export FAKE_FINDING_PATH="sample.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
}

@test "scopes findings for a filename with leading whitespace" {
  # 対象一覧の読み手が strip すると，先頭に空白を持つ名前が別名になり，
  # linter の報告と突合できずに全 findings が消える．
  echo "# lead" > " lead.md"
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_FINDING_PATH=" lead.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "ignores findings in files outside the target set" {
  echo "# new" > new.md
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_TEXTLINT_FINDINGS=1
  export FAKE_FINDING_PATH="sample.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"指摘なし"* ]]
}

@test "drops findings matched by --ignore-glob" {
  echo "# new" > new.md
  export FAKE_MDLINT_FINDINGS=1

  run bash "${SCRIPT}" --ignore-glob "new.md"

  [ "${status}" -eq 0 ]
}

@test "runs textlint even when markdownlint already found problems" {
  echo "# new" > new.md
  export FAKE_MDLINT_FINDINGS=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [ -f "${FAKE_LOG_DIR}/textlint-args" ]
}

@test "exits 2 on a markdownlint execution failure" {
  echo "# new" > new.md
  export FAKE_MDLINT_EXEC_ERROR=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"execution failure"* ]]
}

@test "exits 2 on a textlint execution failure" {
  echo "# new" > new.md
  export FAKE_TEXTLINT_EXEC_ERROR=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"execution failure"* ]]
}

@test "scopes the report to the files given as arguments" {
  echo "# explicit" > explicit.md
  echo "# other" > other.md
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_FINDING_PATH="other.md"

  run bash "${SCRIPT}" explicit.md

  [ "${status}" -eq 0 ]
}

@test "works without the mapfile builtin (bash 3.2 on macOS)" {
  # macOS 同梱の /bin/bash は 3.2 で mapfile を持たない．set -e を使わない
  # 設計のため command-not-found が握り潰され，対象 0 件として lint を
  # 素通りしていた．BASH_ENV で builtin を無効化して同じ条件を作る．
  echo "# new" > new.md
  echo "enable -n mapfile" > "${BATS_TEST_TMPDIR}/no-mapfile.bash"
  export BASH_ENV="${BATS_TEST_TMPDIR}/no-mapfile.bash"
  export FAKE_MDLINT_FINDINGS=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "exits 2 when the target selector fails" {
  # 選定が失敗したのに「対象 0 件」と読み替えると，打ち間違いが lint を
  # 素通りさせる．mapfile は process substitution の状態を継がないため，
  # 明示的に伝播させる必要がある．
  run bash "${SCRIPT}" --base no-such-ref

  [ "${status}" -eq 2 ]
}

@test "normalizes an explicit relative path given from a subdirectory" {
  mkdir -p docs
  echo "# nested" > docs/nested.md
  cd docs
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_FINDING_PATH="docs/nested.md"

  run bash "${SCRIPT}" nested.md

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "normalizes an explicit absolute path" {
  echo "# new" > new.md
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_FINDING_PATH="new.md"

  run bash "${SCRIPT}" "${WORK}/new.md"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "exits 2 when an explicit path does not exist" {
  # 親ディレクトリだけを見ると，打ち間違いが「実在しない 1 件だけを対象に
  # した」形になり，全指摘が絞り込みで消えて 0 終了する．
  mkdir -p docs
  echo "# nested" > docs/nested.md

  run bash "${SCRIPT}" docs/no-such.md

  [ "${status}" -eq 2 ]
}

@test "exits 2 when an explicit path is a directory" {
  mkdir -p docs

  run bash "${SCRIPT}" docs

  [ "${status}" -eq 2 ]
}

@test "exits 2 when an explicit path is outside the repository" {
  run bash "${SCRIPT}" "${BATS_TEST_TMPDIR}/outside.md"

  [ "${status}" -eq 2 ]
}

@test "selects targets by the extension of an explicit --glob" {
  echo "# other" > other.markdown
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_FINDING_PATH="other.markdown"

  run bash "${SCRIPT}" --glob "**/*.markdown"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "covers every tracked markdown with --all" {
  export FAKE_MDLINT_FINDINGS=1
  export FAKE_FINDING_PATH="sample.md"

  run bash "${SCRIPT}" --all

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake mdlint finding"* ]]
}

@test "leaves no generated runtime config in the working tree" {
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  run git status --porcelain
  [[ "${output}" != *"gh-workflows-runtime-"* ]]
}

@test "exits non-zero outside a git worktree" {
  OUTSIDE="${BATS_TEST_TMPDIR}/outside"
  mkdir -p "${OUTSIDE}"
  cd "${OUTSIDE}"

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "reuses the dependency cache on the second run" {
  echo "# new" > new.md
  run bash "${SCRIPT}"
  [ "${status}" -eq 0 ]

  cat > "${FAKE_BIN}/npm" <<'FAKE'
#!/usr/bin/env bash
echo "npm must not be called on cache hit" >&2
exit 9
FAKE
  chmod +x "${FAKE_BIN}/npm"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
}

@test "lints an LF-normalised copy of a CRLF target" {
  # CRLF の作業ツリーでは textlint が行末の CR を 1 字に数え，80 字ちょうどの
  # 文へ sentence-length の指摘が出る．CI（LF checkout）では出ない（Issue #169）．
  printf '# crlf\r\n\r\nこれは CRLF の行である．\r\n' > crlf.md
  export FAKE_INSPECT_FILE="crlf.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "$(cat "${FAKE_LOG_DIR}/textlint-cr")" -eq 0 ]
  [ "$(cat "${FAKE_LOG_DIR}/mdlint-cr")" -eq 0 ]
}

@test "leaves the CRLF line endings of the working tree untouched" {
  # 作業ツリーの改行設定は利用者のものである．lint のために書き換えない．
  printf '# crlf\r\n' > crlf.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "$(tr -dc '\r' < crlf.md | wc -c)" -gt 0 ]
}

@test "maps findings in a nested copy back to the repository path" {
  # 複製の相対構造が崩れると，突合が外れて全指摘が黙って消える．
  mkdir -p docs
  printf '# nested\r\n' > docs/nested.md
  export FAKE_TEXTLINT_FINDINGS=1
  export FAKE_TEXTLINT_ABSOLUTE=1
  export FAKE_FINDING_PATH="docs/nested.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"fake textlint finding"* ]]
}

@test "exits 2 when a finding path cannot be mapped back to the repository" {
  # 剥がせない絶対パスを黙って捨てると「指摘なし」で 0 終了に化ける．
  # Windows では大小文字・8.3 名・ジャンクションで表記が割れうる．
  echo "# new" > new.md
  export FAKE_TEXTLINT_FINDINGS=1
  export FAKE_TEXTLINT_UNMAPPED=1

  run bash "${SCRIPT}"

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"cannot be mapped back"* ]]
}

@test "keeps a lone CR in the linted copy" {
  # 単独の CR は改行ではない．消すと行が連結され，指摘が消えたり増えたりする．
  printf '# cr\r\n\r\nbefore\rafter\r\n' > cr.md
  export FAKE_INSPECT_FILE="cr.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "$(cat "${FAKE_LOG_DIR}/textlint-cr")" -eq 1 ]
}
