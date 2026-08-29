#!/usr/bin/env python3
"""markdownlint-cli2 config から outputFormatters を除去した runtime config を生成する．

composite action は cli2 の既定 formatter 出力（`path:line[:col] RULE 説明`）に
依存する（reviewdog への errorformat 入力と summary 集計の 2 箇所）．
caller config が outputFormatters を定義すると既定 formatter は置き換えられ
（併存しない），lint が走って違反があっても inline・summary とも 0 件になる
（Issue #122）．本スクリプトはキーを除去して既定出力を守り，除去した事実を
Actions アノテーション（::warning::）で caller に知らせる．

引数は 2（src, dest）．環境変数 GITHUB_OUTPUT へ `config=<採用パス>` を
追記する（install-lint-deps.sh と同じ規約）．src に outputFormatters キーが
無いときは dest を生成せず src を採用する（パススルー）．これにより
outputFormatters を使わない caller の挙動は完全に不変となる．
採用パスの分岐まで本スクリプトが担うことで，全経路を pytest で検証できる．

キーがあるときは値を問わず除去する（cli2 は空リストでもキーの存在だけで
既定 formatter を置き換えるため）．YAML の safe_load / safe_dump の往復で
コメントは失われるが，runtime 専用の一時ファイルのため差し支えない．
"""

from __future__ import annotations

import os
import pathlib
import sys
from typing import Sequence

import yaml

OUTPUT_FORMATTERS_WARNING = (
    "::warning::.markdownlint-cli2.yaml の 'outputFormatters' は既定 formatter を"
    "置き換え，PR への inline コメントと summary 集計が 0 件になるため除去しました．"
    "独自 formatter が必要な場合は本 action と別のワークフローで実行してください"
    "（docs/architecture.md 参照）．"
)


def _emit_config_output(path: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        raise ValueError("GITHUB_OUTPUT environment variable is required")
    with open(github_output, "a", encoding="utf-8") as fp:
        fp.write(f"config={path}\n")


def main(argv: Sequence[str]) -> None:
    if len(argv) != 2:
        raise ValueError(f"expected 2 arguments (src, dest), got {len(argv)}")
    src, dest = argv[0], argv[1]

    cfg = yaml.safe_load(pathlib.Path(src).read_text(encoding="utf-8"))
    if cfg is not None and not isinstance(cfg, dict):
        raise TypeError(
            f"markdownlint-cli2 config root must be a mapping, got {type(cfg).__name__}"
        )
    if cfg is None or "outputFormatters" not in cfg:
        # 空ファイルは「設定なし」，キー無しは通常設定．どちらもそのまま渡す．
        _emit_config_output(src)
        return

    del cfg["outputFormatters"]
    print(OUTPUT_FORMATTERS_WARNING)

    dest_path = pathlib.Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    _emit_config_output(dest)


if __name__ == "__main__":
    main(sys.argv[1:])
