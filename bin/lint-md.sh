#!/usr/bin/env bash
# push 前に Markdown を CI と同じ設定で lint する（Issue #134）．
#
# 中央リポジトリ（本スクリプトを含むチェックアウト）の templates と
# .github/actions/markdown-lint/package-lock.json をその場で使う．
# 呼び出し元リポジトリには何も置かない．中央の辞書・ルール更新は
# 次回の実行から全リポジトリのローカル検査へ反映される．
#
# 使い方（呼び出し元リポジトリのどこかで実行する）:
#   bash /path/to/github-workflows/bin/lint-md.sh
#   bash /path/to/github-workflows/bin/lint-md.sh --all
#   bash /path/to/github-workflows/bin/lint-md.sh --base origin/main
#   bash /path/to/github-workflows/bin/lint-md.sh docs/foo.md
#
# 引数:
#   --all                追跡済み Markdown 全件を対象にする
#   --base <ref>         差分の基点を明示する
#   --glob <pattern>     lint 対象の glob（既定 **/*.md．action の markdown-glob と同じ）
#   --ignore-glob <pat>  報告から除外する path glob（action の markdown-ignore と同じ）
#   <files...>           対象を明示する（指定時は差分選定を行わない）
#
# 環境変数:
#   LINT_MD_CACHE_DIR - lint 依存キャッシュの置き場所
#                       既定は ${XDG_CACHE_HOME:-${HOME}/.cache}/github-workflows-md-lint
#
# 終了コード:
#   0  指摘なし（対象 0 件を含む）
#   1  指摘あり
#   2  実行失敗（設定不正・依存導入失敗・lint 自体の異常終了）
#
# CI との対応:
#   lint 自体は composite action と同じく glob 全体へ掛ける．caller 設定の
#   glob 除外（`globs:` の否定パターン）と .textlintignore が効くのは glob
#   実行のときだけであり，変更ファイルだけを引数で渡すと CI と結果がずれる．
#   対象ファイルへの絞り込みは CI の summary と同じ count-lint-findings.py の
#   --diff-files-from に任せる．
#   ただし linter を掛けるのは作業ツリーそのものではなく，対象ファイルを
#   LF 正規化した一時複製である．CRLF の作業ツリーでは textlint が行末の CR を
#   1 字に数え，CI では出ない sentence-length の指摘が出るためである（Issue #169）．
#   差異は終了コードだけである．CI の reviewdog は非ブロッキングだが，
#   ローカルは指摘ありで非 0 終了する．push 前に気づくためのゲートであり，
#   素通ししては用をなさないためである．

set -uo pipefail

CENTRAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="${CENTRAL_ROOT}/templates"
SCRIPTS="${CENTRAL_ROOT}/scripts"
ACTION_DIR="${CENTRAL_ROOT}/.github/actions/markdown-lint"
MARKDOWN_GLOB="**/*.md"

die() {
  echo "lint-md: $1" >&2
  exit 2
}

SELECT_ARGS=()
IGNORE_ARGS=()
FILES=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --all)
      SELECT_ARGS+=("--all")
      shift
      ;;
    --base)
      [ "$#" -ge 2 ] || die "--base requires a ref"
      SELECT_ARGS+=("--base" "$2")
      shift 2
      ;;
    --glob)
      [ "$#" -ge 2 ] || die "--glob requires a pattern"
      MARKDOWN_GLOB="$2"
      shift 2
      ;;
    --ignore-glob)
      [ "$#" -ge 2 ] || die "--ignore-glob requires a pattern"
      IGNORE_ARGS+=("--ignore-glob" "$2")
      shift 2
      ;;
    --help | -h)
      # 先頭のコメント塊をそのまま説明として出す．行番号で切ると本文の
      # 増減でずれるため，最初の非コメント行までを読む．
      awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' \
        "${BASH_SOURCE[0]}"
      exit 0
      ;;
    --)
      shift
      FILES+=("$@")
      break
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      FILES+=("$1")
      shift
      ;;
  esac
done

TOPLEVEL="$(git rev-parse --show-toplevel 2>/dev/null)" ||
  die "not inside a git worktree"

# 明示指定のパスは呼び出し時のカレント基準で書かれる．集計はリポジトリルート
# 相対で突合するため，ルートへ移る前に正規化する．揃えないと，指定した当の
# ファイルの指摘が黙って消える．
if [ "${#FILES[@]}" -gt 0 ]; then
  # 相対化は git 自身に尋ねる．シェルの `pwd` は Windows で /c/... 形式を返す
  # 一方 `rev-parse --show-toplevel` は C:/... 形式を返し，素朴な文字列比較は
  # 成立しない．
  NORMALIZED=()
  for given in "${FILES[@]}"; do
    # 親ディレクトリの存在だけでは足りない．打ち間違いのパスを通すと，
    # 実在しない 1 件だけが対象になり，全指摘が絞り込みで消えて 0 終了する．
    [ -f "${given}" ] || die "no such file: ${given}"
    dir="$(dirname "${given}")"
    file_toplevel="$(git -C "${dir}" rev-parse --show-toplevel 2>/dev/null)" ||
      die "outside the repository: ${given}"
    [ "${file_toplevel}" = "${TOPLEVEL}" ] ||
      die "outside the repository: ${given}"
    prefix="$(git -C "${dir}" rev-parse --show-prefix)" ||
      die "cannot resolve ${given}"
    NORMALIZED+=("${prefix}$(basename "${given}")")
  done
  FILES=("${NORMALIZED[@]}")
fi

cd "${TOPLEVEL}" || die "cannot enter ${TOPLEVEL}"

# 生成・集計スクリプトは PyYAML を使う．環境によって python3 が無い
# （Windows の Git Bash 等）ため，実際に起動できるほうを選ぶ．
PYTHON=""
for candidate in python3 python; do
  if command -v "${candidate}" >/dev/null 2>&1 &&
    "${candidate}" -c "import yaml" >/dev/null 2>&1; then
    PYTHON="${candidate}"
    break
  fi
done
[ -n "${PYTHON}" ] || die "python with PyYAML is required (pip install pyyaml)"

# Windows の Python は，リダイレクト先へ書くとき既定でロケール（cp932 等）を
# 使う．日本語を含む指摘や見出しが化けるため UTF-8 を明示する．
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

WORKDIR="$(mktemp -d)"
MDLINT_GENERATED=""
# runtime config は caller の作業ツリーへ生成されうる（cli2 が相対パスを
# config のディレクトリ基準で解決するため）．終了経路によらず消す．
# 単一引用のため MDLINT_GENERATED は trap 発火時の値で評価される．
# 複製の中で linter を動かすため，消す前にリポジトリルートへ戻る．cwd を
# 抱えたままの rm -rf は Windows で失敗する．
trap 'cd "${TOPLEVEL}" 2>/dev/null; rm -rf "${WORKDIR}"; [ -n "${MDLINT_GENERATED}" ] && rm -f "${MDLINT_GENERATED}"; true' EXIT

TARGETS="${WORKDIR}/targets.txt"
if [ "${#FILES[@]}" -eq 0 ]; then
  # mapfile は process substitution の終了状態を継がない．選定の失敗を
  # 「対象 0 件」と読み替えると，打ち間違いが lint を素通りさせるため，
  # 一度ファイルへ受けて状態を確かめる．
  bash "${SCRIPTS}/list-local-md-targets.sh" --print-base \
    --glob "${MARKDOWN_GLOB}" "${SELECT_ARGS[@]+"${SELECT_ARGS[@]}"}" \
    >"${TARGETS}" || die "failed to list target files"
  # mapfile は bash 4 以降の builtin である．macOS 同梱の /bin/bash は 3.2 で
  # 持たず，set -e を使わない本スクリプトでは command-not-found が握り潰されて
  # 対象 0 件となり，lint を静かに素通りさせる．read ループなら 3.2 でも動く．
  while IFS= read -r selected; do
    [ -n "${selected}" ] && FILES+=("${selected}")
  done <"${TARGETS}"
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "lint-md: nothing to check"
  exit 0
fi

# --glob 指定時は Markdown 以外の変更ファイルも入る．報告の絞り込み集合で
# あって lint 対象そのものではないため「in scope」と呼ぶ．
echo "lint-md: ${#FILES[@]} file(s) in scope"
printf '%s\n' "${FILES[@]}" >"${TARGETS}"

read_output() {
  # GITHUB_OUTPUT 形式のファイルから最後に書かれた値を取り出す．
  grep "^$2=" "$1" | tail -n1 | cut -d= -f2-
}

# --- 設定の解決（composite action と同じ caller-first）---
MDLINT_CFG="$(bash "${SCRIPTS}/resolve-config-path.sh" .markdownlint-cli2.yaml "${TEMPLATES}")" ||
  die "failed to resolve .markdownlint-cli2.yaml"
TEXTLINT_CFG="$(bash "${SCRIPTS}/resolve-config-path.sh" .textlintrc.json "${TEMPLATES}")" ||
  die "failed to resolve .textlintrc.json"
TEXTLINT_IGNORE="$(bash "${SCRIPTS}/resolve-config-path.sh" .textlintignore "${TEMPLATES}")" ||
  die "failed to resolve .textlintignore"
PRH_CFG="$(bash "${SCRIPTS}/resolve-config-path.sh" prh.yml "${TEMPLATES}")" ||
  die "failed to resolve prh.yml"

# caller の設定はリポジトリルート相対で返る．linter は LF 正規化した複製の側で
# 動かすため，相対のままでは解決できない．ここで絶対パスへ寄せる．
absolutize() {
  case "$1" in
    /* | [A-Za-z]:[/\\]*) printf '%s\n' "$1" ;;
    *) printf '%s\n' "${TOPLEVEL}/$1" ;;
  esac
}
MDLINT_CFG="$(absolutize "${MDLINT_CFG}")"
TEXTLINT_CFG="$(absolutize "${TEXTLINT_CFG}")"
TEXTLINT_IGNORE="$(absolutize "${TEXTLINT_IGNORE}")"
PRH_CFG="$(absolutize "${PRH_CFG}")"

# caller root の追加設定は任意．resolve-config-path.sh は「無ければ中央」を
# 返す規約のため流用せず，action と同じく個別に扱う．
ALLOWLIST_CFG=""
[ -f .textlint-allowlist.yml ] && ALLOWLIST_CFG="${TOPLEVEL}/.textlint-allowlist.yml"
PRH_EXTRA_CFG=""
[ -f .prh-extra.yml ] && PRH_EXTRA_CFG="${TOPLEVEL}/.prh-extra.yml"

# --- runtime config の生成 ---
TEXTLINT_RUNTIME="${WORKDIR}/textlintrc.runtime.json"
"${PYTHON}" "${SCRIPTS}/generate-textlint-runtime.py" \
  "${TEXTLINT_CFG}" "${PRH_CFG}" "${TEXTLINT_RUNTIME}" \
  "${ALLOWLIST_CFG}" "${PRH_EXTRA_CFG}" ||
  die "failed to generate the runtime textlint config"

MDLINT_OUT="${WORKDIR}/mdlint.out"
: >"${MDLINT_OUT}"
GITHUB_OUTPUT="${MDLINT_OUT}" "${PYTHON}" \
  "${SCRIPTS}/generate-mdlint-runtime.py" "${MDLINT_CFG}" ||
  die "failed to generate the runtime markdownlint config"
MDLINT_RUNTIME="$(absolutize "$(read_output "${MDLINT_OUT}" config)")"
MDLINT_GENERATED="$(read_output "${MDLINT_OUT}" generated)"
[ -n "${MDLINT_GENERATED}" ] && MDLINT_GENERATED="$(absolutize "${MDLINT_GENERATED}")"

# --- lint 依存の導入（lockfile 鍵つきキャッシュを再利用する）---
CACHE_DIR="${LINT_MD_CACHE_DIR:-${XDG_CACHE_HOME:-${HOME}/.cache}/github-workflows-md-lint}"
mkdir -p "${CACHE_DIR}" || die "cannot create ${CACHE_DIR}"
DEPS_OUT="${WORKDIR}/deps.out"
: >"${DEPS_OUT}"
ACTION_PATH="${ACTION_DIR}" RUNNER_TEMP="${WORKDIR}" GITHUB_OUTPUT="${DEPS_OUT}" \
  LINT_DEPS_CACHE_DIR="${CACHE_DIR}" \
  bash "${SCRIPTS}/install-lint-deps.sh" >"${WORKDIR}/install.log" 2>&1 ||
  { cat "${WORKDIR}/install.log" >&2 && die "failed to install lint dependencies"; }
LINT_BIN="$(read_output "${DEPS_OUT}" bin)"
LINT_MODULES="$(read_output "${DEPS_OUT}" modules)"

# --- LF 正規化した複製の作成（Issue #169）---
# CRLF の作業ツリーでは textlint が行末の CR を 1 字に数え，80 字ちょうどの文へ
# sentence-length の指摘が出る．CI は LF checkout のため出ない．作業ツリーの
# 改行設定は利用者のものなので書き換えず，複製の側で lint する．
#
# 複製へ入れるのは対象ファイルだけでよい．報告は count-lint-findings.py が
# 対象ファイルへ絞るため，対象外のファイルの指摘は元から捨てられている．
# glob と .textlintignore はパスで効くため，相対構造を保つかぎり
# 「lint は glob 全体へ掛ける」という CI との対応は崩れない．
# 変換するのは CRLF の組だけである．単独の CR は改行ではなく，消すと行が
# 連結されて指摘が消えたり増えたりする．末尾改行も足さない（MD047 が見る）．
# 複製に失敗したまま進むと，そのファイルの指摘だけが黙って消えるため，
# 例外は握り潰さず die する．
LINT_ROOT="${WORKDIR}/src"
MIRRORED="$("${PYTHON}" "${SCRIPTS}/normalize-lint-targets.py" \
  "${TARGETS}" "${TOPLEVEL}" "${LINT_ROOT}")" ||
  die "failed to prepare the normalised lint copy"

if [ "${MIRRORED}" -eq 0 ]; then
  echo "lint-md: nothing to check"
  exit 0
fi

cd "${LINT_ROOT}" || die "cannot enter the lint copy"

# --- markdownlint ---
# cli2 は起動に成功すると必ず banner 行を出す．「exit 1 かつ banner あり」
# だけを指摘ありとして扱い，それ以外の非 0 終了は実行失敗とする（action と同じ）．
MDLINT_REPORT="${WORKDIR}/markdownlint-report.txt"
MDLINT_EXIT=0
"${LINT_BIN}/markdownlint-cli2" --config "${MDLINT_RUNTIME}" \
  "${MARKDOWN_GLOB}" "#node_modules" \
  >"${MDLINT_REPORT}" 2>&1 || MDLINT_EXIT=$?
if [ "${MDLINT_EXIT}" -ne 0 ]; then
  if [ "${MDLINT_EXIT}" -ne 1 ] ||
    ! grep -q '^markdownlint-cli2 v' "${MDLINT_REPORT}"; then
    cat "${MDLINT_REPORT}" >&2
    die "markdownlint-cli2 execution failure (exit=${MDLINT_EXIT})"
  fi
fi

# --- textlint ---
# markdownlint に指摘があっても止めない．1 回の実行で両方の指摘を見せ，
# 修正の往復を減らすためである．
export NODE_PATH="${LINT_MODULES}:${NODE_PATH:-}"
TEXTLINT_REPORT="${WORKDIR}/textlint-report.xml"
TEXTLINT_EXIT=0
"${LINT_BIN}/textlint" -f checkstyle --config "${TEXTLINT_RUNTIME}" \
  --ignore-path "${TEXTLINT_IGNORE}" "${MARKDOWN_GLOB}" \
  >"${TEXTLINT_REPORT}" 2>"${WORKDIR}/textlint-stderr.log" || TEXTLINT_EXIT=$?
# 指摘ありなら XML に findings が書かれる．rule 解決失敗等は report が空の
# まま非 0 終了するため，そこだけを実行失敗として切り分ける（action と同じ）．
if [ "${TEXTLINT_EXIT}" -ne 0 ] && [ ! -s "${TEXTLINT_REPORT}" ]; then
  cat "${WORKDIR}/textlint-stderr.log" >&2
  die "textlint execution failure (exit=${TEXTLINT_EXIT})"
fi
[ -s "${WORKDIR}/textlint-stderr.log" ] && cat "${WORKDIR}/textlint-stderr.log" >&2

# --- 対象ファイルへの絞り込みと表示 ---
# 集計は CI の summary と同じスクリプトへ通す．ローカル専用の集計を書くと
# 同じレポートから違う件数が出る余地が生まれるため，表示だけを分ける．
FINDINGS_JSON="${WORKDIR}/findings.json"
# textlint の checkstyle 出力はファイル名を絶対パスで書く．集計側は
# GITHUB_WORKSPACE を prefix として剥がして相対化するため，ここで渡す．
# 剥がす相手は linter を動かした複製のルートである（cwd がそれ）．相対構造は
# リポジトリと同じなので，剥がした結果はリポジトリルート相対のパスになる．
# Git Bash の `pwd` は /c/... 形式を返す一方 textlint は C:\... を出すので，
# 剥がせるよう Windows 形式（pwd -W）を優先する．
WORKSPACE="$(pwd -W 2>/dev/null)" || WORKSPACE="${LINT_ROOT}"
# 剥がせない絶対パスは対象一覧と一致せず，その指摘は黙って捨てられる．
# lint は成功しているため，利用者には「指摘なし」の 0 終了として見える．
# Windows では大小文字・8.3 名・ジャンクションで表記が割れうるため，
# 集計へ渡す前に剥がせることを確かめる．
"${PYTHON}" "${SCRIPTS}/check-report-paths.py" \
  "${TEXTLINT_REPORT}" "${WORKSPACE}" ||
  die "lint findings cannot be mapped back to the repository"

GITHUB_WORKSPACE="${WORKSPACE}" \
  "${PYTHON}" "${SCRIPTS}/count-lint-findings.py" \
  "${TEXTLINT_REPORT}" "${MDLINT_REPORT}" \
  --diff-files-from "${TARGETS}" \
  "${IGNORE_ARGS[@]+"${IGNORE_ARGS[@]}"}" >"${FINDINGS_JSON}" ||
  die "failed to aggregate lint findings"

RENDER_EXIT=0
GITHUB_WORKSPACE="${WORKSPACE}" \
  "${PYTHON}" "${SCRIPTS}/render-local-lint-report.py" <"${FINDINGS_JSON}" ||
  RENDER_EXIT=$?
if [ "${RENDER_EXIT}" -eq 1 ]; then
  echo "lint-md: findings above must be fixed before push" >&2
  exit 1
fi
[ "${RENDER_EXIT}" -eq 0 ] || die "failed to render the lint report"

exit 0
