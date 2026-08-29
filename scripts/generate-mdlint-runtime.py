#!/usr/bin/env python3
"""markdownlint-cli2 config から outputFormatters を除去した runtime config を生成する．

composite action は cli2 の既定 formatter 出力（`path:line[:col] RULE 説明`）に
依存する（reviewdog への errorformat 入力と summary 集計の 2 箇所）．
caller config が outputFormatters を定義すると既定 formatter は置き換えられ
（併存しない），lint が走って違反があっても inline・summary とも 0 件になる
（Issue #122）．本スクリプトはキーを除去して既定出力を守り，除去した事実を
Actions アノテーション（::warning::）で caller に知らせる．

引数は 1（src）．環境変数 GITHUB_OUTPUT へ `config=<採用パス>` と
`generated=<生成パス（生成時のみ）>` を追記する．src に outputFormatters
キーが無いときは何も生成せず src を採用する（パススルー）．これにより
outputFormatters を使わない caller の挙動は完全に不変となる．
採用パスの分岐まで本スクリプトが担うことで，全経路を pytest で検証できる．

runtime ファイルは src と同じディレクトリへ生成する．cli2 は customRules /
markdownItPlugins 等の相対パスを config ファイルのディレクトリ基準で解決する
ため，別ディレクトリへ退避すると caller の独自ルールが読めなくなる（PR #129
の Codex レビュー指摘）．ファイル名は tempfile.mkstemp による一意名とし，
caller 所有の同名ファイルを上書きしない（同レビュー指摘）．suffix は cli2 の
--config が受理する規約（`.markdownlint-cli2.yaml` で終わる名前）に合わせる．
生成物の後始末は呼び出し側が `generated` output を使って行う．

除去はトップレベルキーのテキスト除去で行い，他の行はバイト単位で保持する．
PyYAML の safe_load（YAML 1.1）と cli2 の js-yaml 4（YAML 1.2 系）は
スカラー解釈が異なり，往復再シリアライズでは引用符なしの on / yes 等が
bool へ化けて lint 挙動が変わりうるためである（同レビュー指摘）．
PyYAML はキーの検出と root の型検証のみに使う．
キーがあるときは値を問わず除去する（cli2 は空リストでもキーの存在だけで
既定 formatter を置き換えるため）．
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
from typing import Sequence

import yaml

RUNTIME_PREFIX = ".gh-workflows-runtime-"
RUNTIME_SUFFIX = ".markdownlint-cli2.yaml"

# トップレベル（列 0）の outputFormatters キー行．引用符付きキーも受ける．
_KEY_LINE_RE = re.compile(r"^(?P<quote>['\"]?)outputFormatters(?P=quote)\s*:")

OUTPUT_FORMATTERS_WARNING = (
    "::warning::.markdownlint-cli2.yaml の 'outputFormatters' は既定 formatter を"
    "置き換え，PR への inline コメントと summary 集計が 0 件になるため除去しました．"
    "独自 formatter が必要な場合は本 action と別のワークフローで実行してください"
    "（docs/architecture.md 参照）．"
)


def _emit_outputs(config_path: str, generated_path: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        raise ValueError("GITHUB_OUTPUT environment variable is required")
    with open(github_output, "a", encoding="utf-8") as fp:
        fp.write(f"config={config_path}\n")
        fp.write(f"generated={generated_path}\n")


def _remove_top_level_key(text: str) -> str | None:
    """列 0 の outputFormatters キー行とその継続行（インデント行・空行）を落とす．

    他の行はバイト単位で保持する．キー行を特定できなければ None を返す
    （flow style の root mapping 等．呼び出し側で fail-closed にする）．
    """
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    removed = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if not removed and _KEY_LINE_RE.match(line):
            removed = True
            index += 1
            while index < len(lines) and (
                lines[index].strip() == "" or lines[index][0] in " \t"
            ):
                index += 1
            continue
        kept.append(line)
        index += 1
    if not removed:
        return None
    return "".join(kept)


def main(argv: Sequence[str]) -> None:
    if len(argv) != 1:
        raise ValueError(f"expected 1 argument (src), got {len(argv)}")
    src = argv[0]

    src_path = pathlib.Path(src)
    text = src_path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    if cfg is not None and not isinstance(cfg, dict):
        raise TypeError(
            f"markdownlint-cli2 config root must be a mapping, got {type(cfg).__name__}"
        )
    if cfg is None or "outputFormatters" not in cfg:
        # 空ファイルは「設定なし」，キー無しは通常設定．どちらもそのまま渡す．
        _emit_outputs(src, "")
        return

    stripped = _remove_top_level_key(text)
    if stripped is None:
        # 黙って往復再シリアライズへ落とすと型崩れの恐れがあるため fail-closed．
        raise ValueError(
            "outputFormatters is present but could not be removed textually; "
            "write the config in block style (one top-level key per line)"
        )
    print(OUTPUT_FORMATTERS_WARNING)

    fd, dest = tempfile.mkstemp(
        dir=src_path.parent, prefix=RUNTIME_PREFIX, suffix=RUNTIME_SUFFIX
    )
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fp:
        fp.write(stripped)
    _emit_outputs(dest, dest)


if __name__ == "__main__":
    main(sys.argv[1:])
