#!/usr/bin/env bash
# ローカル作業ツリーで lint すべき Markdown の一覧を stdout へ出す（Issue #134）．
# bin/lint-md.sh が push 前検査の対象を決めるために呼ぶ．
#
# 引数:
#   --all            追跡済みの Markdown をすべて出す
#   --base <ref>     差分の基点を明示する
#   --glob <pattern> lint 対象 glob．渡されたときは拡張子で絞らない
#   --print-base     解決した基点を stderr へ 1 行出す
#
# 仕様:
#   - カレントが git worktree でなければ非 0 終了する
#   - 基点の解決順は --base > @{upstream} > origin/HEAD > origin/main > HEAD．
#     push 前検査という用途上，既定の基点は「push 先が既に持っている状態」が
#     最も近い．upstream が未設定のローカルブランチでは remote の既定ブランチ
#     へ落とし，remote が無い（単独リポジトリ）ときのみ HEAD を使う．
#     HEAD はコミット済みの変更を含まないため，最後の手段である．
#   - 既定の対象は「基点との差分」＋「untracked」の Markdown である．
#     コミット済み・staged・unstaged のいずれも 1 度の diff で拾える
#   - 削除されたファイルは出さない．実在しないパスを lint へ渡さないためである．
#     除くのは削除だけで，型変更（symlink から通常ファイルへの置き換え等）は
#     中身が入れ替わっているため対象に含める
#   - パスはリポジトリルート相対で 1 行 1 ファイル．重複なし・辞書順
#   - 非 ASCII のパスをエスケープせずに出す．git の既定（core.quotePath）は
#     C 形式の 8 進エスケープを出すが，その値は linter の報告（実 UTF-8 パス）と
#     突合できず，指摘が黙って消える
#   - --glob を渡さないときの選定は md 固定である．
#     --glob を渡したときは，その拡張子で選ぶ．lint 対象 glob を変えた
#     caller で，対象が 1 件も選ばれない事態を防ぐ．
#     `{md,markdown}` の brace 記法は展開する．git の pathspec は展開しない
#     ため，合成した `*.{md,markdown}` では 1 件も一致しない．
#     拡張子を持たない指定（`README`・`**/LICENSE`）や解釈しきれない記法では
#     絞り込みをやめ，変更ファイルをすべて出す．md へ落とすと取りこぼす．
#     ディレクトリ部は選定へ使わない．絞り込みは後段の集計が行うため，
#     多めに選んでも害はなく，少なく選ぶと指摘を取りこぼすからである
#
# stdout:
#   対象ファイルのパス（0 件のときは何も出さず 0 終了）

set -euo pipefail

ALL=0
BASE=""
GLOB=""
PRINT_BASE=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)
      ALL=1
      shift
      ;;
    --print-base)
      PRINT_BASE=1
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

# --glob を渡さないときだけ *.md で絞る．既定の用途はこれで，Markdown を
# 触っていない push では linter を起動せずに済む．
# --glob を渡されたときは絞り込まない．glob の解釈（拡張子・brace・文字
# クラス）を選定側で再実装すると，取りこぼす方向の穴が開き続ける．実際に
# 拡張子と brace の解釈で 2 度取りこぼした．選定は「linter の報告を絞り込む
# 集合」を作るだけで指摘の発生源ではないため，多めに選んでも後段が落とす．
PATHSPECS=('*.md')
if [ -n "${GLOB}" ]; then
  PATHSPECS=()
fi

# core.quotePath=false で 8 進エスケープを止める．caller の設定を書き換えず，
# 本スクリプトの git 呼び出しにだけ効かせる．
git_raw() {
  git -c core.quotePath=false "$@"
}

if [ "${ALL}" -eq 1 ]; then
  git_raw ls-files -- ${PATHSPECS[@]+"${PATHSPECS[@]}"} | sort -u
  exit 0
fi

if [ -n "${BASE}" ]; then
  if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
    echo "unknown ref: ${BASE}" >&2
    exit 1
  fi
else
  # origin/HEAD は clone 時に設定され，既定ブランチが main でない
  # リポジトリでも解決する．origin/main だけを見ると，master や develop の
  # caller で HEAD へ落ちてしまう．git diff HEAD はコミット済みの変更を
  # 含まないため，コミットしてから実行すると対象 0 件で黙って終わる．
  for candidate in '@{upstream}' 'origin/HEAD' 'origin/main' 'HEAD'; do
    if git rev-parse --verify --quiet "${candidate}^{commit}" >/dev/null; then
      BASE="${candidate}"
      break
    fi
  done
fi

# 基点は結果を大きく変える．どれが選ばれたかを見えるようにする．
# HEAD へ落ちたことに気づけないと，対象 0 件を「変更なし」と読み違える．
if [ "${PRINT_BASE}" -eq 1 ]; then
  echo "base = ${BASE:-(none)}" >&2
fi

{
  # 基点が 1 つも解決できないのは commit の無いリポジトリだけである．
  # その場合は untracked だけが対象になる．
  if [ -n "${BASE}" ]; then
    # 除きたいのは削除（D）だけなので，小文字の d で「削除以外すべて」を
    # 指定する．ACMR の列挙では型変更（T．追跡済みの symlink が通常
    # ファイルへ置き換わった等）が漏れ，中身が入れ替わっているのに
    # 対象から外れていた．
    git_raw diff --name-only --diff-filter=d "${BASE}" -- ${PATHSPECS[@]+"${PATHSPECS[@]}"}
  fi
  git_raw ls-files --others --exclude-standard -- ${PATHSPECS[@]+"${PATHSPECS[@]}"}
} | sort -u
