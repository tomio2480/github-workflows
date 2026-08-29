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

while [ $# -gt 0 ]; do
  case "$1" in
    --notes)
      NOTES="${2:?--notes requires a value}"
      shift 2
      ;;
    --notes-file)
      NOTES_FILE="${2:?--notes-file requires a value}"
      shift 2
      ;;
    --delete-branch)
      DELETE_BRANCH="${2:?--delete-branch requires a value}"
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

# ハイフン始まりはオプション誤解釈（例: --all）を招くため拒否する
if [ -n "${DELETE_BRANCH}" ] && [[ "${DELETE_BRANCH}" == -* ]]; then
  echo "error: invalid branch name: ${DELETE_BRANCH}" >&2
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

run_cmd git tag -f "${MAJOR}" "${VERSION}"

# 並行実行時に古いリリースが major mutable を巻き戻さないよう，
# push 直前の remote 値を lease に指定する（値が動いていれば push は失敗する）
REMOTE_MAJOR_SHA="$(git ls-remote origin "refs/tags/${MAJOR}" | cut -f1)"
if [ -n "${REMOTE_MAJOR_SHA}" ]; then
  run_cmd git push "--force-with-lease=refs/tags/${MAJOR}:${REMOTE_MAJOR_SHA}" origin "${MAJOR}"
else
  run_cmd git push origin "${MAJOR}"
fi

if [ -n "${DELETE_BRANCH}" ]; then
  run_cmd git push origin --delete "${DELETE_BRANCH}"
fi

if [ "${DRY_RUN}" -eq 1 ]; then
  echo "dry-run: no changes were made"
else
  echo "released ${VERSION} and moved ${MAJOR}"
fi
