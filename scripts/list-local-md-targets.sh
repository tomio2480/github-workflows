#!/usr/bin/env bash
# ローカル作業ツリーで lint すべき Markdown の一覧を stdout へ出す（Issue #134）．
# bin/lint-md.sh が push 前検査の対象を決めるために呼ぶ．
#
# 引数:
#   --all         追跡済みの Markdown をすべて出す
#   --base <ref>  差分の基点を明示する
#
# 仕様:
#   - カレントが git worktree でなければ非 0 終了する
#   - 基点の解決順は --base > @{upstream} > origin/main > HEAD である．
#     push 前検査という用途上，既定の基点は「push 先が既に持っている状態」が
#     最も近い．upstream が未設定のローカルブランチでは origin/main へ落とし，
#     どちらも無い（clone 直後・単独リポジトリ）ときのみ HEAD を使う．
#   - 既定の対象は「基点との差分」＋「untracked」の Markdown である．
#     コミット済み・staged・unstaged のいずれも 1 度の diff で拾える
#   - 削除されたファイルは出さない．実在しないパスを lint へ渡さないためである
#   - パスはリポジトリルート相対で 1 行 1 ファイル．重複なし・辞書順
#
# stdout:
#   対象ファイルのパス（0 件のときは何も出さず 0 終了）

set -euo pipefail

ALL=0
BASE=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)
      ALL=1
      shift
      ;;
    --base)
      if [ "$#" -lt 2 ]; then
        echo "--base requires a ref" >&2
        exit 2
      fi
      BASE="$2"
      shift 2
      ;;
    *)
      echo "unknown option: $1" >&2
      echo "usage: $0 [--all] [--base <ref>]" >&2
      exit 2
      ;;
  esac
done

if ! TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "not inside a git worktree" >&2
  exit 1
fi
cd "${TOPLEVEL}"

# 出力の並びを環境の locale に左右させない．テストと実行結果を一致させる．
export LC_ALL=C

if [ "${ALL}" -eq 1 ]; then
  git ls-files -- '*.md' | sort -u
  exit 0
fi

if [ -n "${BASE}" ]; then
  if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
    echo "unknown ref: ${BASE}" >&2
    exit 1
  fi
else
  for candidate in '@{upstream}' 'origin/main' 'HEAD'; do
    if git rev-parse --verify --quiet "${candidate}^{commit}" >/dev/null; then
      BASE="${candidate}"
      break
    fi
  done
fi

{
  # 基点が 1 つも解決できないのは commit の無いリポジトリだけである．
  # その場合は untracked だけが対象になる．
  if [ -n "${BASE}" ]; then
    # ACMR は追加・コピー・変更・改名のみを拾う．削除（D）を除くことで
    # 実在しないパスが lint へ渡らない．
    git diff --name-only --diff-filter=ACMR "${BASE}" -- '*.md'
  fi
  git ls-files --others --exclude-standard -- '*.md'
} | sort -u
