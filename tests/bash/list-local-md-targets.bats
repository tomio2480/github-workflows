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

@test "includes a file whose type changed" {
  # 追跡済みの symlink が通常ファイルへ置き換わると git は T を返す．
  # ACMR だけを見ると，中身が入れ替わっているのに対象から漏れる．
  # 実体の symlink を作らずに同じ状態を作るため，index へ 120000 の
  # エントリを直接入れる．Windows でも同じ検査ができる．
  git config core.symlinks true
  BLOB="$(printf 'base.md' | git hash-object -w --stdin)"
  git update-index --add --cacheinfo "120000,${BLOB},link.md"
  git commit -q -m "add link.md as a symlink"
  printf '# real\n' > link.md

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "link.md" ]
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

@test "resolves the base from origin/HEAD when upstream is unset" {
  # 既定ブランチが main でない caller で origin/main しか見ないと HEAD へ
  # 落ちる．git diff HEAD はコミット済みの変更を含まないため，コミットして
  # から実行すると対象 0 件で黙って終わる．
  SRC="${BATS_TEST_TMPDIR}/src"
  git init -q -b master "${SRC}"
  git -C "${SRC}" config core.autocrlf false
  echo "# seed" > "${SRC}/seed.md"
  git -C "${SRC}" add -A
  git -C "${SRC}" commit -q -m "initial"

  CLONE="${BATS_TEST_TMPDIR}/clone"
  # checkout 時点から改行変換を止める．後から設定すると，既存ファイルが
  # CRLF で展開済みとなり差分として現れてしまう．
  git clone -q -c core.autocrlf=false "${SRC}" "${CLONE}"
  cd "${CLONE}"
  git switch -q -c feature
  echo "# committed" > committed.md
  git add -A
  git commit -q -m "add committed.md"

  run bash "${SCRIPT}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "committed.md" ]
}

@test "reports the resolved base with --print-base" {
  run bash "${SCRIPT}" --print-base --base HEAD

  [ "${status}" -eq 0 ]
  # run は stderr も output へ取り込む．
  [[ "${output}" == *"base = HEAD"* ]]
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

@test "selects every changed file when --glob is given" {
  # glob の解釈（拡張子・brace・文字クラス）を選定側で再実装すると，
  # 取りこぼす方向の穴が開き続ける．--glob を渡されたら絞り込まない．
  echo "# a" > a.md
  echo "# b" > b.markdown
  echo "readme" > README

  run bash "${SCRIPT}" --glob "**/*.{md,markdown}"

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"a.md"* ]]
  [[ "${output}" == *"b.markdown"* ]]
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
