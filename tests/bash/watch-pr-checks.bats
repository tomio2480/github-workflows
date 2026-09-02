#!/usr/bin/env bats

# bin/watch-pr-checks.sh の単体テスト．
#
# 仕様（Issue #133）:
#   - 引数: <pr-number> と任意の --timeout / --interval / --expect-sha
#   - 監視対象の commit は origin の実体（git ls-remote）を正とする
#   - gh の headRefOid が実体へ追いつくまで待つ
#   - checks は自前で polling する．1 件以上あり，pending が無く，
#     件数が前回から増えていない状態になるまで待つ
#   - 監視の後に head が動いていないことを確認する
#   - 終了コード: 0 全 pass / 1 入力・環境エラー / 2 タイムアウト・commit 不一致 /
#     3 checks の失敗
#   - git / gh はスタブで置き換え，発行コマンドの列を検証する

setup() {
  REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
  SCRIPT="${REPO_ROOT}/bin/watch-pr-checks.sh"
  STUB_DIR="${BATS_TEST_TMPDIR}/stubs"
  export CMD_LOG="${BATS_TEST_TMPDIR}/cmd.log"
  export STUB_STATE_DIR="${BATS_TEST_TMPDIR}/state"
  mkdir -p "${STUB_DIR}" "${STUB_STATE_DIR}"
  : > "${CMD_LOG}"

  REMOTE_SHA="1111111111111111111111111111111111111111"
  STALE_SHA="2222222222222222222222222222222222222222"
  export REMOTE_SHA STALE_SHA

  # git スタブ: ls-remote だけ挙動を持ち，他は記録して成功する．
  cat > "${STUB_DIR}/git" <<'STUB'
#!/usr/bin/env bash
echo "git $*" >> "${CMD_LOG}"
if [ "$1" = "ls-remote" ]; then
  # STUB_REMOTE_EMPTY=1 で「ブランチが remote に無い」を再現する．
  [ "${STUB_REMOTE_EMPTY:-0}" = "1" ] && exit 0
  printf '%s\t%s\n' "${REMOTE_SHA}" "$3"
  exit 0
fi
exit 0
STUB
  chmod +x "${STUB_DIR}/git"

  # gh スタブ: pr view と pr checks を呼び出し回数で制御する．
  #   STUB_GH_LAG        gh が古い SHA を返し続ける回数
  #   STUB_CHECKS_LAG    checks が未登録（出力なし）の回数
  #   STUB_CHECKS        pass / fail / pending / late / growing
  #   STUB_HEAD_MOVES    checks が出そろった後の headRefOid を別 commit にする
  cat > "${STUB_DIR}/gh" <<'STUB'
#!/usr/bin/env bash
echo "gh $*" >> "${CMD_LOG}"
bump() {
  local file="${STUB_STATE_DIR}/$1"
  local n=0
  [ -f "${file}" ] && n="$(cat "${file}")"
  n=$((n + 1))
  echo "${n}" > "${file}"
  echo "${n}"
}
case "$1 $2" in
  "pr view")
    if [[ "$*" == *headRefName* ]]; then
      echo "feature/example"
      exit 0
    fi
    if [[ "$*" == *headRefOid* ]]; then
      # checks を 1 度でも照会した後は「監視の後」とみなす
      if [ "${STUB_HEAD_MOVES:-0}" = "1" ] && [ -f "${STUB_STATE_DIR}/checks" ]; then
        echo "${STALE_SHA}"
        exit 0
      fi
      n="$(bump view)"
      if [ "${n}" -le "${STUB_GH_LAG:-0}" ]; then
        echo "${STALE_SHA}"
      else
        echo "${REMOTE_SHA}"
      fi
      exit 0
    fi
    exit 0
    ;;
  "pr checks")
    n="$(bump checks)"
    lag="${STUB_CHECKS_LAG:-0}"
    if [ "${n}" -le "${lag}" ]; then
      # 未登録は出力なし（gh は非 0 で終えるが，出力だけを見る仕様）
      exit 8
    fi
    case "${STUB_CHECKS:-pass}" in
      fail)
        printf 'pass\nfail\n'
        ;;
      pending)
        # 最初の 2 回だけ pending を含む
        if [ "${n}" -le $((lag + 2)) ]; then
          printf 'pending\npass\n'
        else
          printf 'pass\npass\n'
        fi
        ;;
      late)
        # 1 件だけ遅れて登録される
        if [ "${n}" -le $((lag + 1)) ]; then
          printf 'pass\n'
        else
          printf 'pass\npass\n'
        fi
        ;;
      growing)
        # 照会のたびに 1 件増え続け，件数が安定しない
        i=0
        while [ "${i}" -lt "${n}" ]; do
          echo "pass"
          i=$((i + 1))
        done
        ;;
      *)
        printf 'pass\npass\n'
        ;;
    esac
    exit 8
    ;;
esac
exit 0
STUB
  chmod +x "${STUB_DIR}/gh"

  export PATH="${STUB_DIR}:${PATH}"
}

checks_queries() {
  grep -c "gh pr checks" "${CMD_LOG}"
}

# --- 入力検証 ---

@test "rejects non-numeric PR number" {
  run bash "${SCRIPT}" abc

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"pr-number"* ]]
}

@test "rejects missing PR number" {
  run bash "${SCRIPT}"

  [ "${status}" -eq 1 ]
}

@test "rejects unknown option" {
  run bash "${SCRIPT}" 165 --nope

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"unknown option"* ]]
}

@test "rejects option-like token as --timeout value" {
  run bash "${SCRIPT}" 165 --timeout --interval 0

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"--timeout"* ]]
}

@test "rejects --expect-sha that is not a full SHA" {
  run bash "${SCRIPT}" 165 --expect-sha abc1234

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"SHA"* ]]
}

# --- remote の実体を正とする ---

@test "fails when the branch is absent from the remote" {
  STUB_REMOTE_EMPTY=1 run bash "${SCRIPT}" 165 --interval 0 --timeout 0

  [ "${status}" -eq 1 ]
  [[ "${output}" == *"origin"* ]]
  run grep -q "gh pr checks" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

@test "uses --expect-sha instead of consulting the remote" {
  run bash "${SCRIPT}" 165 --interval 0 --timeout 30 --expect-sha "${REMOTE_SHA}"

  [ "${status}" -eq 0 ]
  run grep -q "^git ls-remote" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

# --- gh がリモートへ追いつくまで待つ ---

@test "waits for gh to report the remote commit before querying checks" {
  STUB_GH_LAG=2 run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 0 ]
  count="$(grep -c -- "--json headRefOid" "${CMD_LOG}")"
  [ "${count}" -ge 3 ]
}

@test "times out without querying checks when gh never catches up" {
  STUB_GH_LAG=99 run bash "${SCRIPT}" 165 --interval 0 --timeout 0

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"${REMOTE_SHA}"* ]]
  run grep -q "gh pr checks" "${CMD_LOG}"
  [ "${status}" -ne 0 ]
}

# --- checks が出そろうまで待つ ---

@test "waits for checks to be registered" {
  STUB_CHECKS_LAG=2 run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 0 ]
  run checks_queries
  [ "${output}" -ge 3 ]
}

@test "times out when no check is ever registered" {
  STUB_CHECKS_LAG=99 run bash "${SCRIPT}" 165 --interval 0 --timeout 0

  [ "${status}" -eq 2 ]
}

@test "keeps polling while a check is pending" {
  STUB_CHECKS=pending run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 0 ]
  run checks_queries
  [ "${output}" -ge 3 ]
}

@test "keeps polling until the check set stops growing" {
  # 別 workflow の登録が遅れる場合，先に見えた check だけで完了と読まない
  STUB_CHECKS=late run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"all 2 checks passed"* ]]
}

@test "times out when checks keep appearing" {
  STUB_CHECKS=growing run bash "${SCRIPT}" 165 --interval 0 --timeout 0

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"${REMOTE_SHA}"* ]]
}

# --- 判定 ---

@test "reports the inspected commit on success" {
  run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 0 ]
  [[ "${output}" == *"${REMOTE_SHA}"* ]]
}

@test "exits 3 when a check failed" {
  STUB_CHECKS=fail run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 3 ]
  [[ "${output}" == *"${REMOTE_SHA}"* ]]
}

@test "fails when the head moved while watching" {
  STUB_HEAD_MOVES=1 run bash "${SCRIPT}" 165 --interval 0 --timeout 30

  [ "${status}" -eq 2 ]
  [[ "${output}" == *"${STALE_SHA}"* ]]
}
