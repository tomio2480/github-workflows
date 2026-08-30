#!/usr/bin/env bash

# PR マージ後の定例 patch リリースを 1 コマンドで実行する．
#
# 実行列（docs/notes/2026-05-01-retroactive-tag-rollout.md の実績手順に準拠）:
#   1. git tag <version> <merge-sha>
#   2. git push origin <version>
#   3. gh release create <version> --title <version> --notes(-file) ...
#      タグを先に push 済みのため --target は付けない
#      （既存タグへの --target は HTTP 422 で失敗する）
#   4. git tag -f <major> <version>      # major mutable を最新 patch へ追従
#   5. git push --force-with-lease=refs/tags/<major>:<remote 現在値> origin <major>
#      並行実行による巻き戻りを防ぐ．remote 未存在の初回のみ通常 push
#   6. （任意）git push origin --delete <branch>
#
# 途中失敗後は同一コマンドの再実行で再開できる（作成済みのタグ・Release は
# スキップする）．
# 版番号の決定（最新タグ確認・patch/minor 判断）はスクリプト外の責務とする．

set -euo pipefail

usage() {
  cat >&2 <<'USAGE'
Usage: release-patch.sh <version> <merge-sha> (--notes TEXT | --notes-file PATH)
                        [--delete-branch NAME] [--dry-run]

  version        vX.Y.Z 形式の patch バージョン（例: v2.12.5）
  merge-sha      リリース対象マージコミットのフル SHA（40 桁）
  --notes        リリースノート本文（1 行程度の短文向け）
  --notes-file   リリースノートのファイルパス（複数行の既定手段）
  --delete-branch  マージ済みブランチを origin から削除する
  --dry-run      実行せずコマンド列を表示する（ガード検証のみ実行）
USAGE
  exit 1
}

VERSION="${1:-}"
SHA="${2:-}"
[ $# -ge 2 ] || usage
shift 2

NOTES=""
NOTES_FILE=""
DELETE_BRANCH=""
DRY_RUN=0

# 値必須オプションが後続オプションを値として吸うと，--dry-run 指定の欠落が
# 本実行へ化けるため，ハイフン始まりと空値を拒否する
require_value() {
  if [ -z "${2:-}" ] || [[ "${2}" == -* ]]; then
    echo "error: $1 requires a value" >&2
    exit 1
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --notes)
      require_value --notes "${2:-}"
      NOTES="$2"
      shift 2
      ;;
    --notes-file)
      require_value --notes-file "${2:-}"
      NOTES_FILE="$2"
      shift 2
      ;;
    --delete-branch)
      require_value --delete-branch "${2:-}"
      DELETE_BRANCH="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage
      ;;
  esac
done

# --- 入力検証（意味的に具体的 → 汎用的の順） ---

if ! [[ "${VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: version must match vX.Y.Z: ${VERSION}" >&2
  exit 1
fi

# v1 系は self-detection bug により凍結中（動かさない不変条件）．
# 根拠は CLAUDE.md・docs/security.md・docs/fork-usage.md を参照
if [[ "${VERSION}" == v1.* ]]; then
  echo "error: the v1 series is frozen and must not move: ${VERSION}" >&2
  exit 1
fi

if ! [[ "${SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "error: merge-sha must be a full 40-hex SHA: ${SHA}" >&2
  exit 1
fi

if [ -z "${NOTES}" ] && [ -z "${NOTES_FILE}" ]; then
  echo "error: release notes are required (--notes or --notes-file)" >&2
  exit 1
fi

if [ -n "${NOTES}" ] && [ -n "${NOTES_FILE}" ]; then
  echo "error: use either --notes or --notes-file, not both" >&2
  exit 1
fi

if [ -n "${NOTES_FILE}" ] && [ ! -f "${NOTES_FILE}" ]; then
  echo "error: notes file not found: ${NOTES_FILE}" >&2
  exit 1
fi

# ハイフン始まりはオプション誤解釈（例: --all）を招くため拒否する．
# refs/ 始まりは refs/heads/ を前置する削除 refspec と二重になるため拒否する
# （refs/tags/... 誤指定によるタグ削除の防止を兼ねる）
if [ -n "${DELETE_BRANCH}" ] && [[ "${DELETE_BRANCH}" == -* || "${DELETE_BRANCH}" == refs/* ]]; then
  echo "error: invalid branch name (short name expected): ${DELETE_BRANCH}" >&2
  exit 1
fi

MAJOR="${VERSION%%.*}"

# --- ガード（読み取り専用のため dry-run でも実行する） ---

# 既存タグが要求 SHA を指す場合は途中失敗からの再開とみなし，
# タグ作成だけスキップして残りの手順を続行する（冪等な再実行）．
RESUME_TAG=0
EXISTING_TAG_SHA="$(git rev-parse -q --verify "refs/tags/${VERSION}^{commit}" || true)"
if [ -n "${EXISTING_TAG_SHA}" ]; then
  if [ "${EXISTING_TAG_SHA}" = "${SHA}" ]; then
    echo "note: tag ${VERSION} already points at the requested commit; resuming"
    RESUME_TAG=1
  else
    echo "error: tag ${VERSION} already exists at a different commit: ${EXISTING_TAG_SHA}" >&2
    exit 1
  fi
fi

if ! git cat-file -e "${SHA}^{commit}" 2> /dev/null; then
  echo "error: commit not found in local repository: ${SHA}" >&2
  exit 1
fi

# --- 実行 ---

# 失敗時の中断は set -e に依存する．run_cmd の呼び出しを条件式や
# パイプの一部へ変えると set -e が効かなくなるため，形を変えない．
run_cmd() {
  if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[dry-run] $*"
  else
    echo "+ $*"
    "$@"
  fi
}

if [ "${RESUME_TAG}" -eq 0 ]; then
  run_cmd git tag "${VERSION}" "${SHA}"
fi
run_cmd git push origin "${VERSION}"

# 再実行時に作成済み Release で失敗しないよう存在確認する（読み取り専用）
if gh release view "${VERSION}" > /dev/null 2>&1; then
  echo "note: release ${VERSION} already exists; skipping create"
elif [ -n "${NOTES_FILE}" ]; then
  run_cmd gh release create "${VERSION}" --title "${VERSION}" --notes-file "${NOTES_FILE}"
else
  run_cmd gh release create "${VERSION}" --title "${VERSION}" --notes "${NOTES}"
fi

# 並行実行時に古いリリースが major mutable を巻き戻さないよう，二段で守る．
# 1) 単調性検査: remote の現在値が新 patch commit の祖先であることを確認する．
#    祖先でない（= remote が先へ進んでいる）場合は巻き戻りになるため中止する．
#    lease は「観測値からの変化」しか検知せず，版の順序は保証しないため必要．
# 2) lease: 検査済みの観測値を期待値に指定し，push までの間の移動を検知する．
REMOTE_MAJOR_SHA="$(git ls-remote origin "refs/tags/${MAJOR}" | cut -f1)"
if [ -n "${REMOTE_MAJOR_SHA}" ]; then
  # dry-run では fetch しない（FETCH_HEAD・object db への書き込みを避ける）．
  # commit がローカルに無く検査できない場合は，本実行時に検査される旨を示す
  if [ "${DRY_RUN}" -eq 1 ] && ! git cat-file -e "${REMOTE_MAJOR_SHA}^{commit}" 2> /dev/null; then
    echo "[dry-run] (monotonicity check for ${MAJOR} deferred to a real run)"
  else
    if [ "${DRY_RUN}" -eq 0 ]; then
      # shallow クローンでは remote タグと新 patch の間の履歴が欠けており，
      # 祖先関係を判定できない（実際は祖先でも非祖先と誤判定される）．
      # そのため深さを解消してから fetch する
      if [ "$(git rev-parse --is-shallow-repository)" = "true" ]; then
        git fetch --quiet --unshallow origin "refs/tags/${MAJOR}"
      else
        git fetch --quiet origin "refs/tags/${MAJOR}"
      fi
    fi
    if ! git merge-base --is-ancestor "${REMOTE_MAJOR_SHA}" "${SHA}"; then
      echo "error: remote ${MAJOR} (${REMOTE_MAJOR_SHA}) is ahead of ${SHA}; refusing to rewind" >&2
      exit 1
    fi
  fi
fi

run_cmd git tag -f "${MAJOR}" "${VERSION}"

if [ -n "${REMOTE_MAJOR_SHA}" ]; then
  run_cmd git push "--force-with-lease=refs/tags/${MAJOR}:${REMOTE_MAJOR_SHA}" origin "${MAJOR}"
else
  run_cmd git push origin "${MAJOR}"
fi

if [ -n "${DELETE_BRANCH}" ]; then
  # refspec を refs/heads/ 明示で組み，タグ等の別種 ref を誤削除しない
  run_cmd git push origin --delete "refs/heads/${DELETE_BRANCH}"
fi

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "dry-run: no changes were made"
else
  echo "released ${VERSION} and moved ${MAJOR}"
fi
