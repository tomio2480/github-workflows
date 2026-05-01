#!/usr/bin/env python3
"""textlint と markdownlint の検査結果から件数を集計し JSON を stdout に出す．

composite action の summary 投稿ステップで呼ばれる．集計と投稿の責務分離のため
本スクリプトは「読んで数えて JSON にする」 までを担当し，PR コメント投稿は別の
post-lint-summary.sh が担当する．

usage:
    count-lint-findings.py <textlint-xml> <markdownlint-txt> > summary.json

入力:
    <textlint-xml>     textlint の checkstyle 形式レポート
    <markdownlint-txt> markdownlint-cli2 の stderr 取り込みテキスト

出力（stdout，JSON）:
    {
      "markdownlint": {"total": N},
      "textlint": {"error": N, "warning": N, "info": N, "total": N}
    }

挙動:
    - 入力ファイルが存在しないときは件数 0 として扱う（fail-open）．composite
      action の経路上で，前段ステップが skip された等で生成されないケースに
      備える
    - textlint XML が parse 不能のときは ValueError．こちらは「実行はしたが
      壊れたデータを掴んでいる」 状態なので早期失敗させる
    - markdownlint テキストの finding 行は「path:line[:col] RULE/...」 を満たす
      行で同定する．banner（"Finding:" "Linting:" "Summary:"）は除外される
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence


_MARKDOWNLINT_FINDING = re.compile(r"^.+:\d+(?::\d+)?\s+\S+/\S+")


def count_textlint(path: Path) -> dict[str, int]:
    """checkstyle XML を読み severity 別件数を返す．"""
    if not Path(path).is_file():
        return {"error": 0, "warning": 0, "info": 0, "total": 0}

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"failed to parse textlint XML: {path}") from e

    counts = {"error": 0, "warning": 0, "info": 0}
    for error in tree.getroot().iter("error"):
        sev = (error.get("severity") or "").lower()
        if sev in counts:
            counts[sev] += 1
    counts["total"] = sum(counts.values())
    return counts


def count_markdownlint(path: Path) -> dict[str, int]:
    """markdownlint-cli2 のテキストレポートから finding 行数を返す．"""
    if not Path(path).is_file():
        return {"total": 0}

    total = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if _MARKDOWNLINT_FINDING.match(line):
                total += 1
    return {"total": total}


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        raise ValueError("usage: count-lint-findings.py <textlint-xml> <markdownlint-txt>")

    payload = {
        "markdownlint": count_markdownlint(Path(argv[1])),
        "textlint": count_textlint(Path(argv[0])),
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
