#!/usr/bin/env python3
"""textlint と markdownlint の検査結果から件数と findings 一覧を集計し JSON を stdout に出す．

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
      "markdownlint": {
        "total": N,
        "findings": [{"file": str, "line": int, "rule": str, "message": str}, ...]
      },
      "textlint": {
        "error": N, "warning": N, "info": N, "total": N,
        "findings": [{"file": str, "line": int, "severity": str, "rule": str, "message": str}, ...]
      }
    }

挙動:
    - 入力ファイルが存在しないときは件数 0 / 空 findings として扱う（fail-open）．
      composite action の経路上で前段ステップが skip された等で生成されない
      ケースに備える
    - textlint XML が parse 不能のときは ValueError．こちらは「実行はしたが
      壊れたデータを掴んでいる」 状態なので早期失敗させる
    - markdownlint テキストの finding 行は「path:line[:col] RULE/...」 を満たす
      行で同定する．banner（"Finding:" "Linting:" "Summary:"）は除外される．
      path 部分は非貪欲（non-greedy）でマッチさせ，ファイル名にコロンを含む
      環境でも左端の `path:line` を正しく拾う
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence


_MARKDOWNLINT_LINE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::\d+)?\s+(?P<rule>\S+/\S+)(?:\s+(?P<message>.*))?$"
)


def count_textlint(path: Path) -> dict:
    """checkstyle XML を読み severity 別件数と findings 一覧を返す．"""
    empty = {"error": 0, "warning": 0, "info": 0, "total": 0, "findings": []}
    if not Path(path).is_file():
        return empty

    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        raise ValueError(f"failed to parse textlint XML: {path}") from e

    counts = {"error": 0, "warning": 0, "info": 0}
    findings: list[dict] = []
    for file_el in tree.getroot().iter("file"):
        file_name = file_el.get("name") or ""
        for error in file_el.iter("error"):
            sev = (error.get("severity") or "").lower()
            if sev in counts:
                counts[sev] += 1
            try:
                line_no = int(error.get("line") or 0)
            except ValueError:
                line_no = 0
            findings.append(
                {
                    "file": file_name,
                    "line": line_no,
                    "severity": sev,
                    "rule": error.get("source") or "",
                    "message": error.get("message") or "",
                }
            )
    counts["total"] = sum(counts.values())
    counts["findings"] = findings
    return counts


def count_markdownlint(path: Path) -> dict:
    """markdownlint-cli2 のテキストレポートから件数と findings 一覧を返す．"""
    if not Path(path).is_file():
        return {"total": 0, "findings": []}

    findings: list[dict] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _MARKDOWNLINT_LINE.match(line.rstrip("\r\n"))
            if not m:
                continue
            try:
                line_no = int(m.group("line"))
            except ValueError:
                line_no = 0
            findings.append(
                {
                    "file": m.group("file"),
                    "line": line_no,
                    "rule": m.group("rule"),
                    "message": (m.group("message") or "").strip(),
                }
            )
    return {"total": len(findings), "findings": findings}


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
