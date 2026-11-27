#!/usr/bin/env bash
# markdownlint-cli2 のテキストレポートを errorformat で reviewdog へ渡す．
# composite action の投稿ステップと自己テスト（-reporter=local で解析結果を
# 確かめる）の両方から呼び，errorformat の定義をここ 1 か所に保つ．
#
# 使い方:
#   reviewdog-markdownlint.sh <report> [reviewdog へ渡す追加引数...]
#
# finding 行は `path:line[:col] [severity] RULE 説明` の形をとる．
# severity（error / warning）は cli2 0.24 系の既定 formatter が挟む語である．
# `%*[a-z]` で読み飛ばし，message へ混ぜない．`%t` で拾うと reviewdog が
# 指摘ごとに重大度を持ち，caller の level input と表示がずれるため使わない．
# severity の無い旧形式の 2 行は，形式が戻った場合の受け皿として残す．
# banner や Summary などの非 finding 行はどれにも一致せず無視される．
#
# 終了コードは reviewdog のものをそのまま返す．

set -uo pipefail

report="${1:?usage: reviewdog-markdownlint.sh <report> [reviewdog args...]}"
shift

exec reviewdog \
  -efm="%f:%l:%c %*[a-z] %m" \
  -efm="%f:%l %*[a-z] %m" \
  -efm="%f:%l:%c %m" \
  -efm="%f:%l %m" \
  -name="markdownlint" \
  "$@" <"${report}"
