#!/usr/bin/env bash
# textlint / markdownlint / prh の config ファイルパスを解決する．
# caller root（PWD）に同名ファイルがあればそれを採用し，無ければ中央 templates を返す．
# 引数:
#   $1: basename（例: .markdownlint-cli2.yaml）
#   $2: 中央 templates ディレクトリの絶対パスまたは相対パス
# 出力:
#   採用するパス文字列を stdout に 1 行で出力．
#   両方の引数が揃っている場合は戻り値 0．
#   引数不足の場合は set -u により非 0 終了し，stderr にエラーが出る．

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <basename> <central_templates_dir>" >&2
  exit 2
fi

basename="$1"
central_templates_dir="$2"

if [ -f "${basename}" ]; then
  echo "${basename}"
else
  echo "${central_templates_dir}/${basename}"
fi