#!/usr/bin/env bash
# ローカル作業ツリーで lint すべき Markdown の一覧を stdout へ出す（Issue #134）．
# bin/lint-md.sh が push 前検査の対象を決めるために呼ぶ．
#
# 引数:
#   --all            追跡済みの Markdown をすべて出す
#   --base <ref>     差分の基点を明示する
#   --glob <pattern> lint 対象 glob．拡張子だけを選定へ使う
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
#   - 非 ASCII のパスをエスケープせずに出す．git の既定（core.quotePath）は
#     C 形式の 8 進エスケープを出すが，その値は linter の報告（実 UTF-8 パス）と
#     突合できず，指摘が黙って消える
#   - 選定する拡張子は既定で md とし，--glob に拡張子があればそれを使う．
#     lint 対象 glob を変えた caller で，対象が 1 件も選ばれない事態を防ぐ．
#     ディレクトリ部は選定へ使わない．絞り込みは後段の集計が行うため，
#     多めに選んでも害はなく，少なく選ぶと指摘を取りこぼすからである
#
# stdout:
#   対象ファイルのパス（0 件のときは何も出さず 0 終了）

set -euo pipefail

ALL=0
BASE=""
GLOB=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)
      ALL=1
      shift
      ;;
    --glob)
      if [ "$#" -lt 2 ]; then
        echo "--glob requires a pattern" >&2
        exit 2
      fi
      GLOB="$2"
      shift 2
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
      echo "usage: $0 [--all] [--base <ref>] [--glob <pattern>]" >&2
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

# 拡張子は glob の末尾から取る．`docs` のように最後のセグメントへ `.` が
# 無いときは既定の md を使う．
PATHSPEC='*.md'
GLOB_TAIL="${GLOB##*/}"
if [ -n "${GLOB}" ] && [ "${GLOB_TAIL}" != "${GLOB_TAIL#*.}" ]; then
  PATHSPEC="*.${GLOB_TAIL##*.}"
fi

# core.quotePath=false で 8 進エスケープを止める．caller の設定を書き換えず，
# 本スクリプトの git 呼び出しにだけ効かせる．
git_raw() {
  git -c core.quotePath=false "$@"
}

if [ "${ALL}" -eq 1 ]; then
  git_raw ls-files -- "${PATHSPEC}" | sort -u
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
    git_raw diff --name-only --diff-filter=ACMR "${BASE}" -- "${PATHSPEC}"
  fi
  git_raw ls-files --others --exclude-standard -- "${PATHSPEC}"
} | sort -u
