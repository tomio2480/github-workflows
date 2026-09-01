#!/usr/bin/env bats

# scripts/list-local-md-targets.sh unit tests.
#
# Spec:
#   Arguments:
#     --all           - すべての追跡済み Markdown を出す
#     --base <ref>    - 差分の基点を明示する
#     --glob <pattern> - 選定する拡張子を lint 対象 glob から決める
#   Behavior:
#     - カレントが git worktree でなければ非 0 終了
#     - 基点の解決順は --base > @{upstream} > origin/main > HEAD
#     - 既定は「基点との差分」＋「untracked」の Markdown を出す
#     - 削除されたファイルは出さない（実在するものだけを lint 対象にする）
#     - パスはリポジトリルート相対で 1 行 1 ファイル．重複なし・辞書順
#     - 非 ASCII のパスをエスケープせずそのまま出す
#     - 既定の拡張子は md．--glob の拡張子があればそちらを使う
#
# Test strategy:
#   BATS_TEST_TMPDIR に使い捨ての git リポジトリを作り，実際の git を動かす．
#   コミット作者は環境変数で与え，利用者の global 設定に依存させない．

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/list-local-md-targets.sh"

  export GIT_AUTHOR_NAME="test"
  export GIT_AUTHOR_EMAIL="test@example.com"
  export GIT_COMMITTER_NAME="test"
  export GIT_COMMITTER_EMAIL="test@example.com"

  WORK="${BATS_TEST_TMPDIR}/work"
  mkdir -p "${WORK}"
  cd "${WORK}"
  git init -q -b main .
  # bats の run は stderr も output へ取り込む．Windows の既定設定では git が
  # 改行変換の警告を出し，出力の完全一致検査を壊す．fixture 側で無効化する．
  git config core.autocrlf false
  echo "# base" > base.md
  echo "not markdown" > base.txt
  git add -A
  git commit -q -m "initial"
}

@test "exits non-zero outside a git worktree" {
  OUTSIDE="${BATS_TEST_TMPDIR}/outside"
  mkdir -p "${OUTSIDE}"
  cd "${OUTSIDE}"

  run bash "${SCRIPT}"

  [ "${status}" -ne 0 ]
}

@test "lists every tracked markdown with --all" {
  run bash "${SCRIPT}" --all

  [ "${status}" -eq 0 ]
  [ "${output}" = "base.md" ]
}

@test "lists modified and untracked markdown by default" {
  echo "changed" >> base.md
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"base.md"* ]]
  [[ "${output}" == *"new.md"* ]]
}

@test "excludes non-markdown files" {
  echo "changed" >> base.txt
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [[ "${output}" != *"base.txt"* ]]
  [ "${output}" = "new.md" ]
}

@test "excludes deleted files" {
  git rm -q base.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ -z "${output}" ]
}

@test "includes staged additions" {
  echo "# staged" > staged.md
  git add staged.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "staged.md" ]
}

@test "lists commits made since the given --base" {
  echo "# committed" > committed.md
  git add committed.md
  git commit -q -m "add committed.md"

  run bash "${SCRIPT}" --base HEAD~1

  [ "${status}" -eq 0 ]
  [ "${output}" = "committed.md" ]
}

@test "exits non-zero when --base names an unknown ref" {
  run bash "${SCRIPT}" --base no-such-ref

  [ "${status}" -ne 0 ]
}

@test "exits non-zero when --base is given without a value" {
  run bash "${SCRIPT}" --base

  [ "${status}" -ne 0 ]
}

@test "exits non-zero on an unknown option" {
  run bash "${SCRIPT}" --nope

  [ "${status}" -ne 0 ]
}

@test "outputs repository-root-relative paths from a subdirectory" {
  mkdir -p docs
  echo "# nested" > docs/nested.md
  cd docs

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "docs/nested.md" ]
}

@test "emits non-ASCII paths unescaped" {
  # core.quotePath の既定では git が C 形式の 8 進エスケープを出す．その値を
  # 対象一覧へ書くと linter の報告（実際の UTF-8 パス）と突合できない．
  git config core.quotePath true
  echo "# 日本語" > 日本語.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "日本語.md" ]
}

@test "selects by the extension of an explicit --glob" {
  echo "# other" > other.markdown

  run bash "${SCRIPT}" --glob "**/*.markdown"

  [ "${status}" -eq 0 ]
  [ "${output}" = "other.markdown" ]
}

@test "keeps selecting markdown when --glob is not given" {
  echo "# other" > other.markdown
  echo "# new" > new.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "new.md" ]
}

@test "selects every extension of a brace --glob" {
  # git の pathspec は brace 展開をしない．`*.{md,markdown}` を合成すると
  # 1 件も一致せず，lint を起動しないまま素通りする．
  echo "# a" > a.md
  echo "# b" > b.markdown

  run bash "${SCRIPT}" --glob "**/*.{md,markdown}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"a.md"* ]]
  [[ "${output}" == *"b.markdown"* ]]
}

@test "selects every changed file when --glob is not a simple extension" {
  # 解釈しきれない glob では絞り込まない．多めに選んでも後段の集計が
  # 落とすだけだが，少なく選ぶと指摘を取りこぼす．
  echo "# a" > a.md
  echo "# b" > b.markdown

  run bash "${SCRIPT}" --glob "**/*.m[dk]"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"a.md"* ]]
  [[ "${output}" == *"b.markdown"* ]]
}

@test "selects every changed file when --glob has no extension" {
  # `README` や `**/LICENSE` は妥当な指定である．md へ落とすと，指定した
  # ファイルが選ばれないまま lint を起動せず終了する．
  echo "# new" > new.md
  echo "readme" > README

  run bash "${SCRIPT}" --glob "**/README"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"README"* ]]
}

@test "keeps the markdown default when --glob is absent" {
  echo "# new" > new.md
  echo "readme" > README

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "new.md" ]
}

@test "exits non-zero when --glob is given without a value" {
  run bash "${SCRIPT}" --glob

  [ "${status}" -ne 0 ]
}

@test "emits each path once and in sorted order" {
  echo "# a" > a.md
  echo "# b" > b.md
  echo "changed" >> base.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "$(printf 'a.md\nb.md\nbase.md')" ]
}
