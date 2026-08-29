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
    # shallow 判定．既定は「完全クローン」= false．
    if [ "$2" = "--is-shallow-repository" ]; then
      [ "${STUB_SHALLOW:-0}" = "1" ] && echo "true" || echo "false"
      exit 0
    fi
    # refs/tags/<version> の存在確認．既定は「未存在」= exit 1．
    # 存在時は STUB_TAG_SHA（既定は要求と異なる SHA）を出力する．
    if [ "${STUB_TAG_EXISTS:-0}" = "1" ]; then
      echo "${STUB_TAG_SHA:-ffffffffffffffffffffffffffffffffffffffff}"
      exit 0
    fi
    exit 1
    ;;
  cat-file)
    # commit 実在確認．既定は「存在する」= exit 0．
    [ "${STUB_COMMIT_MISSING:-0}" = "1" ] && exit 1
    exit 0
    ;;
  ls-remote)
    # remote major タグの現在値．既定は存在（lease 付き push の経路）．
    if [ -n "${STUB_REMOTE_MAJOR_SHA-1111111111111111111111111111111111111111}" ]; then
      printf '%s\trefs/tags/%s\n' \
        "${STUB_REMOTE_MAJOR_SHA:-1111111111111111111111111111111111111111}" "$3"
    fi
    exit 0
    ;;
  merge-base)
    # 単調性検査．既定は「remote は新 patch の祖先」= exit 0．
    [ "${STUB_MAJOR_NOT_ANCESTOR:-0}" = "1" ] && exit 1
    exit 0
    ;;
esac
exit 0
STUB
  chmod +x "${STUB_DIR}/git"

  # gh スタブ: 呼び出しを記録して成功を返す．release view は既定「未存在」．
  cat > "${STUB_DIR}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "${CMD_LOG}"
if [ "$1 $2" = "release view" ]; then
  [ "${STUB_RELEASE_EXISTS:-0}" = "1" ] && exit 0
  exit 1
fi
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

@test "rejects option-like token as --notes value" {
  # --notes の値欠落で後続オプションを吸うと dry-run が本実行に化けるため拒否する
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes --dry-run

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"--notes"* ]]
  run grep -q "^git tag" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

@test "rejects option-like token as --notes-file value" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file --dry-run

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"--notes-file"* ]]
}

@test "rejects frozen v1 series version" {
  run bash "${SCRIPT}" v1.2.3 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"v1"* ]]
  run grep -q "^git tag" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

@test "rejects branch name starting with dash" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" \
    --delete-branch --all

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"branch"* ]]
}

# --- ガード ---

@test "fails when tag already exists with a different commit" {
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
  # ガード 2 件（rev-parse / cat-file）の後に定例コマンドが並ぶ
  mapfile -t lines < "${CMD_LOG}"
  [ "${lines[2]}" = "git tag v2.12.5 ${SHA}" ]
  [ "${lines[3]}" = "git push origin v2.12.5" ]
  [ "${lines[4]}" = "gh release view v2.12.5" ]
  [ "${lines[5]}" = "gh release create v2.12.5 --title v2.12.5 --notes-file ${NOTES_FILE}" ]
  [ "${lines[6]}" = "git ls-remote origin refs/tags/v2" ]
  [ "${lines[7]}" = "git rev-parse --is-shallow-repository" ]
  [ "${lines[8]}" = "git fetch --quiet origin refs/tags/v2" ]
  [ "${lines[9]}" = "git merge-base --is-ancestor 1111111111111111111111111111111111111111 ${SHA}" ]
  [ "${lines[10]}" = "git tag -f v2 v2.12.5" ]
  [ "${lines[11]}" = "git push --force-with-lease=refs/tags/v2:1111111111111111111111111111111111111111 origin v2" ]
  [ "${#lines[@]}" -eq 12 ]
}

@test "deepens shallow clone before the ancestry check" {
  export STUB_SHALLOW=1

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  # 切り詰められた履歴では祖先関係を判定できないため深さを解消してから検査する
  grep -qx "git fetch --quiet --unshallow origin refs/tags/v2" "${CMD_LOG}"
  run grep -qx "git fetch --quiet origin refs/tags/v2" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

# --- 再開可能性（Codex P2 指摘 3887143551） ---

@test "resumes when existing tag already points at requested SHA" {
  export STUB_TAG_EXISTS=1
  export STUB_TAG_SHA="${SHA}"

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  # タグ作成はスキップし，push 以降は実行する
  run grep -qx "git tag v2.12.5 ${SHA}" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
  grep -qx "git push origin v2.12.5" "${CMD_LOG}"
  grep -q "gh release create v2.12.5" "${CMD_LOG}"
}

@test "skips release creation when release already exists" {
  export STUB_RELEASE_EXISTS=1

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  run grep -q "gh release create" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
  grep -qx "git tag -f v2 v2.12.5" "${CMD_LOG}"
}

# --- mutable tag の並行保護（Codex P2 指摘 3887143552） ---

@test "refuses to move major tag when remote is not an ancestor" {
  export STUB_MAJOR_NOT_ANCESTOR=1

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"rewind"* ]]
  # major mutable にはローカル・remote とも触れない
  run grep -q "git tag -f v2" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
  run grep -q "origin v2$" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

@test "pushes major tag without lease when remote tag is absent" {
  export STUB_REMOTE_MAJOR_SHA=""

  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  grep -qx "git push origin v2" "${CMD_LOG}"
  run grep -q -- "--force-with-lease" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

@test "release create does not use --target" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  run grep -q -- "--target" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

@test "derives major mutable tag from version" {
  run bash "${SCRIPT}" v3.0.1 "${SHA}" --notes-file "${NOTES_FILE}"

  [ "${status}" -eq 0 ]
  grep -qx "git tag -f v3 v3.0.1" "${CMD_LOG}"
  grep -qx "git push --force-with-lease=refs/tags/v3:1111111111111111111111111111111111111111 origin v3" \
    "${CMD_LOG}"
}

@test "passes inline notes with --notes" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes "one-line note"

  [ "${status}" -eq 0 ]
  grep -qx "gh release create v2.12.5 --title v2.12.5 --notes one-line note" "${CMD_LOG}"
}

@test "deletes merged branch with explicit refs/heads refspec" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" \
    --delete-branch feat/some-branch

  [ "${status}" -eq 0 ]
  grep -qx "git push origin --delete refs/heads/feat/some-branch" "${CMD_LOG}"
}

@test "rejects delete-branch value that is a fully qualified ref" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" \
    --delete-branch refs/tags/v2.12.5

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"branch"* ]]
}

@test "dry-run prints commands without executing mutations" {
  run bash "${SCRIPT}" v2.12.5 "${SHA}" --notes-file "${NOTES_FILE}" --dry-run

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"git push origin v2.12.5"* ]]
  # ガード（読み取り専用）以外は実行されない
  run grep -q "^git tag" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
  run grep -q "^git push" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
  run grep -q "^gh release create" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
  # fetch はローカル（FETCH_HEAD・object db）へ書き込むため dry-run では行わない
  run grep -q "^git fetch" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}
