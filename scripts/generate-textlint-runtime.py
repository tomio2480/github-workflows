#!/usr/bin/env python3
"""textlint config の prh.rulePaths を絶対パスに差し替え，必要なら caller の
.textlint-allowlist.yml を filters.allowlist に inject した runtime config を生成する．

caller の textlintrc と中央の prh.yml を組み合わせると相対パスが意図どおりに解決されない
ため，本スクリプトで `.textlintrc.runtime.json` を作成して action から渡す．

rules.prh を対象にパスを解決する．
caller が prh を意図的に false または未定義にしている場合は尊重し，書き換えない．
`overrides` は textlint 本体が実装していないため書き換えず，警告のみ出す（Issue #85）．

argv 4 つ目（optional）に caller root の .textlint-allowlist.yml の絶対パスが渡されると，
その内容を filters.allowlist に inject する．空文字または argv 3 つの呼び出しでは
filters は変更しない（後方互換）．
allowlist に `allow` と `allowlistConfigPaths` 以外の鍵があれば，内容は素通ししつつ
警告のみ出す（Issue #98）．

argv 5 つ目（optional）に caller root の .prh-extra.yml の絶対パスが渡されると，
rules.prh.rulePaths を [中央 prh, 追加辞書] の 2 本にする（Issue #91）．
textlint-rule-prh は同一パターンの衝突を先に並べた辞書で解決するため，
中央を先頭に固定し，caller は語を「足す」だけにする．
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Sequence

OVERRIDES_WARNING = (
    "::warning::.textlintrc.json の 'overrides' は textlint が実装していないため無視されます．"
    "per-path の文体切り替えには <!-- textlint-disable --> コメントか "
    ".textlintignore を使ってください（docs/rule-rationale.md 参照）．"
)

# textlint-filter-rule-allowlist が解釈する鍵．これ以外は黙って無視されるため，
# 誤記（例: allowRules）を caller へ警告で知らせる（Issue #98）．
ALLOWLIST_KNOWN_KEYS = frozenset({"allow", "allowlistConfigPaths"})

ALLOWLIST_UNKNOWN_KEY_WARNING = (
    "::warning::.textlint-allowlist.yml の鍵 '{keys}' は "
    "textlint-filter-rule-allowlist が解釈しないため無視されます．"
    "有効な鍵は 'allow' と 'allowlistConfigPaths' です（docs/dictionary-maintenance.md 参照）．"
)


def _resolve_prh_rule(
    prh_rule, prh_abs: str, context_path: str, prh_extra_abs: str = ""
) -> None:
    """prh_rule が dict なら rulePaths を prh_abs（と prh_extra_abs）で上書きする．
    None / False のときは caller の意図を尊重して何もしない．それ以外は TypeError．
    """
    if isinstance(prh_rule, dict):
        rule_paths = [prh_abs]
        if prh_extra_abs:
            rule_paths.append(prh_extra_abs)
        prh_rule["rulePaths"] = rule_paths
    elif prh_rule is None or prh_rule is False:
        pass
    else:
        raise TypeError(
            f"textlint config '{context_path}' must be an object or false"
        )


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
    # 引用符なしの数値・真偽値キーは PyYAML が int / bool として読むため，
    # 混在ソートの TypeError を避ける目的で文字列へそろえてから並べる．
    unknown_keys = sorted(
        str(key) for key in body if key not in ALLOWLIST_KNOWN_KEYS
    )
    if unknown_keys:
        # overrides 警告（Issue #85）と同型．内容は書き換えず素通しし，
        # 「効いていない」ことを Actions アノテーションで caller に知らせる．
        print(ALLOWLIST_UNKNOWN_KEY_WARNING.format(keys="', '".join(unknown_keys)))
    return body


def _resolve_prh_extra(path_str: str) -> str:
    """caller 追加辞書のパスを検証し絶対パスを返す．空文字なら空文字のまま返す．"""
    if not path_str:
        return ""
    path = pathlib.Path(path_str)
    if not path.is_file():
        raise ValueError(f"prh extra dictionary not found: {path_str}")
    return str(path.resolve())


def main(argv: Sequence[str]) -> None:
    if len(argv) not in (3, 4, 5):
        raise ValueError(
            "expected 3 to 5 arguments (src, prh, dest, [allowlist], [prh-extra]), "
            f"got {len(argv)}"
        )
    src, prh, dest = argv[0], argv[1], argv[2]
    allowlist_path = argv[3] if len(argv) >= 4 else ""
    prh_extra_path = argv[4] if len(argv) == 5 else ""

    cfg = json.loads(pathlib.Path(src).read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError(
            f"textlint config root must be a JSON object, got {type(cfg).__name__}"
        )

    rules = cfg.get("rules", {})
    if not isinstance(rules, dict):
        raise TypeError("textlint config 'rules' must be an object")

    prh_abs = str(pathlib.Path(prh).resolve())
    prh_extra_abs = _resolve_prh_extra(prh_extra_path)
    _resolve_prh_rule(rules.get("prh"), prh_abs, "rules.prh", prh_extra_abs)

    if cfg.get("overrides"):
        # textlint（15.6.0 時点）は overrides を実装していない．書き換えず素通しし，
        # 「効いていない」ことを Actions アノテーションで caller に知らせる（Issue #85）．
        print(OVERRIDES_WARNING)

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
