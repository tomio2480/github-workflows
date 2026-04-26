#!/usr/bin/env python3
"""textlint config の rules.prh.rulePaths を絶対パスに差し替える runtime config を生成する．

caller の textlintrc と中央の prh.yml を組み合わせると相対パスが意図どおりに解決されない
ため，本スクリプトで `.textlintrc.runtime.json` を作成して action から渡す．

caller が rules.prh を意図的に false または未定義にしている場合は尊重し，書き換えない．
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Sequence


def main(argv: Sequence[str]) -> None:
    src, prh, dest = argv[0], argv[1], argv[2]
    cfg = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))

    rules = cfg.get("rules", {})
    if not isinstance(rules, dict):
        raise TypeError("textlint config 'rules' must be an object")

    prh_rule = rules.get("prh")
    if isinstance(prh_rule, dict):
        prh_rule["rulePaths"] = [str(pathlib.Path(prh).resolve())]
    elif prh_rule is None or prh_rule is False:
        # caller が prh を未定義または false（無効化）にしている場合はそのまま尊重する
        pass
    else:
        raise TypeError("textlint config 'rules.prh' must be an object or false")

    pathlib.Path(dest).write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1:])