#!/usr/bin/env bats

# bin/release-patch.sh の単体テスト．
#
# 仕様:
#   - 引数: <version> <merge-sha> と notes 指定（--notes TEXT か --notes-file PATH）
#   - 動作: patch タグ作成 → push → GitHub Release 作成 →
#     major mutable タグ追従（force push）→ 任意でマージ済みブランチ削除
#   - タグは先に作成・push し，gh release create に --target は付けない
#     （既存タグへの --target は HTTP 422 で失敗するため）
#   - 版番号の決定はスクリプト外の責務．形式検証のみ行う
#   - git / gh はスタブで置き換え，発行コマンドの列を検証する

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/bin/release-patch.sh"
  STUB_DIR="${BATS_TEST_TMPDIR}/stubs"
  export CMD_LOG="${BATS_TEST_TMPDIR}/cmd.log"
  mkdir -p "${STUB_DIR}"
  : > "${CMD_LOG}"

  # git スタブ: 呼び出しを記録し，ガード系サブコマンドだけ挙動を制御する．
  cat > "${STUB_DIR}/git" <<'STUB'
#!/usr/bin/env bash
echo "git $*" >> "${CMD_LOG}"
case "$1" in
  rev-parse)
    # refs/tags/<version> の存在確認．既定は「未存在」= exit 1．
    [ "${STUB_TAG_EXISTS:-0}" = "1" ] && exit 0
    exit 1
    ;;
  cat-file)
    # commit 実在確認．既定は「存在する」= exit 0．
    [ "${STUB_COMMIT_MISSING:-0}" = "1" ] && exit 1
    exit 0
    ;;
esac
exit 0
STUB
  chmod +x "${STUB_DIR}/git"

  # gh スタブ: 呼び出しを記録して成功を返す．
  cat > "${STUB_DIR}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "${CMD_LOG}"
exit 0
STUB
  chmod +x "${STUB_DIR}/gh"

  export PATH="${STUB_DIR}:${PATH}"

  NOTES_FILE="${BATS_TEST_TMPDIR}/notes.md"
  echo "release notes body" > "${NOTES_FILE}"
  SHA="0123456789abcdef0123456789abcdef01234567"
}

# --- 入力検証 ---

@test "rejects version without vX.Y.Z format" {
  run bash "${SCRIPT}" v2.12 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"version"* ]]
}

@test "rejects non-full-length SHA" {
  run bash "${SCRIPT}" v2.12.5 abc1234 --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"SHA"* ]]
}

@test "rejects missing notes option" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"notes"* ]]
}

@test "rejects missing notes file" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${BATS_TEST_TMPDIR}/no-such.md"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"notes"* ]]
}

@test "rejects branch name starting with dash" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" \
    --delete-branch --all

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"branch"* ]]
}

# --- ガード ---

@test "fails when tag already exists" {
  export STUB_TAG_EXISTS=1

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"v2.12.5"* ]]
}

@test "fails when commit does not exist" {
  export STUB_COMMIT_MISSING=1

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"commit"* ]]
}

# --- 実行列 ---

@test "runs documented release sequence in order" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  # ガード 2 件（rev-parse / cat-file）の後に定例 5 コマンドが並ぶ
  mapfile -t lines < "${CMD_LOG}"
  [ "${lines[2]}" = "git tag v2.12.5 ${SHA}" ]
  [ "${lines[3]}" = "git push origin v2.12.5" ]
  [ "${lines[4]}" = "gh release create v2.12.5 --title v2.12.5 --notes-file ${NOTES_FILE}" ]
  [ "${lines[5]}" = "git tag -f v2 v2.12.5" ]
  [ "${lines[6]}" = "git push -f origin v2" ]
  [ "${#lines[@]}" -eq 7 ]
}

@test "release create does not use --target" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  ! grep -q -- "--target" "${CMD_LOG}"
}

@test "derives major mutable tag from version" {
  run bash "${SCRIPT}" v3.0.1 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  grep -qx "git tag -f v3 v3.0.1" "${CMD_LOG}"
  grep -qx "git push -f origin v3" "${CMD_LOG}"
}

@test "passes inline notes with --notes" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes "one-line note"

  [ "${status}" -eq 0 ]
  grep -qx "gh release create v2.12.5 --title v2.12.5 --notes one-line note" "${CMD_LOG}"
}

@test "deletes merged branch when --delete-branch is given" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" \
    --delete-branch feat/some-branch

  [ "${status}" -eq 0 ]
  grep -qx "git push origin --delete feat/some-branch" "${CMD_LOG}"
}

@test "dry-run prints commands without executing mutations" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" --dry-run

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"git push origin v2.12.5"* ]]
  # ガード（読み取り専用）以外は実行されない
  ! grep -q "^git tag" "${CMD_LOG}"
  ! grep -q "^git push" "${CMD_LOG}"
  ! grep -q "^gh " "${CMD_LOG}"
}
