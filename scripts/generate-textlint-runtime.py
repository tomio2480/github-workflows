#!/usr/bin/env python3
"""textlint config の rules.prh.rulePaths を絶対パスに差し替え，必要なら caller の
.textlint-allowlist.yml を filters.allowlist に inject した runtime config を生成する．

caller の textlintrc と中央の prh.yml を組み合わせると相対パスが意図どおりに解決されない
ため，本スクリプトで `.textlintrc.runtime.json` を作成して action から渡す．

caller が rules.prh を意図的に false または未定義にしている場合は尊重し，書き換えない．

argv 4 つ目（optional）に caller root の .textlint-allowlist.yml の絶対パスが渡されると，
その内容を filters.allowlist に inject する．空文字または argv 3 つの呼び出しでは
filters は変更しない（後方互換）．
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Sequence


def _load_allowlist(path_str: str) -> dict:
    path = pathlib.Path(path_str)
    if not path.is_file():
        raise ValueError(
            f"allowlist file not found: {path_str}"
        )
    import yaml  # 遅延 import．argv 3 つの呼び出しでは PyYAML を要求しない．

    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise TypeError(
            f"allowlist YAML root must be a mapping, got {type(body).__name__}"
        )
    return body


def main(argv: Sequence[str]) -> None:
    if len(argv) not in (3, 4):
        raise ValueError(
            f"expected 3 or 4 arguments (src, prh, dest, [allowlist]), got {len(argv)}"
        )
    src, prh, dest = argv[0], argv[1], argv[2]
    allowlist_path = argv[3] if len(argv) == 4 else ""

    cfg = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError(
            f"textlint config root must be a JSON object, got {type(cfg).__name__}"
        )

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

    if allowlist_path:
        allowlist = _load_allowlist(allowlist_path)
        filters = cfg.setdefault("filters", {})
        if not isinstance(filters, dict):
            raise TypeError("textlint config 'filters' must be an object")
        filters["allowlist"] = allowlist

    pathlib.Path(dest).write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
