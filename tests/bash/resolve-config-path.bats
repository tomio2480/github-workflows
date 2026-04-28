#!/usr/bin/env bats

# scripts/resolve-config-path.sh の単体テスト．
#
# 仕様:
#   - 引数: <basename> <central_templates_dir>
#   - 動作: PWD（=caller root 想定）に <basename> があればそのパス，
#     無ければ <central_templates_dir>/<basename> を出力する
#   - 標準エラー出力には何も出さない
#   - 戻り値は常に 0（後段で「ファイルが存在しない」エラーを別経路で出させる）

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/scripts/resolve-config-path.sh"
  CALLER_ROOT="${BATS_TEST_TMPDIR}/caller"
  CENTRAL_DIR="${BATS_TEST_TMPDIR}/central/templates"
  mkdir -p "${CALLER_ROOT}" "${CENTRAL_DIR}"
}

# caller root に同名ファイルがあれば caller 側のパスを返す
@test "returns caller path when file exists in caller root" {
  cd "${CALLER_ROOT}"
  : > "${CALLER_ROOT}/.markdownlint-cli2.yaml"
  : > "${CENTRAL_DIR}/.markdownlint-cli2.yaml"

  run bash "${SCRIPT}" .markdownlint-cli2.yaml "${CENTRAL_DIR}"

  [ "${status}" -eq 0 ]
  [ "${output}" = ".markdownlint-cli2.yaml" ]
}

# caller root に無ければ central のパスを返す
@test "returns central path when file is missing from caller root" {
  cd "${CALLER_ROOT}"
  : > "${CENTRAL_DIR}/.textlintrc.json"

  run bash "${SCRIPT}" .textlintrc.json "${CENTRAL_DIR}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "${CENTRAL_DIR}/.textlintrc.json" ]
}

# caller にも central にも無くても central のパスを返す（後段で別エラーになる挙動を維持）
@test "returns central path even when neither caller nor central has the file" {
  cd "${CALLER_ROOT}"

  run bash "${SCRIPT}" prh.yml "${CENTRAL_DIR}"

  [ "${status}" -eq 0 ]
  [ "${output}" = "${CENTRAL_DIR}/prh.yml" ]
}