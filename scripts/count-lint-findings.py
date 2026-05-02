#!/usr/bin/env python3
"""textlint と markdownlint の検査結果から件数と findings 一覧を集計し JSON を stdout に出す．

composite action の summary 投稿ステップで呼ばれる．集計と投稿の責務分離のため
本スクリプトは「読んで数えて JSON にする」 までを担当し，PR コメント投稿は別の
post-lint-summary.sh が担当する．

usage:
    count-lint-findings.py <textlint-xml> <markdownlint-txt> [--ignore-glob PATTERN ...]

入力:
    <textlint-xml>     textlint の checkstyle 形式レポート
    <markdownlint-txt> markdownlint-cli2 の stderr 取り込みテキスト
    --ignore-glob      集計から除外する path glob．繰り返し指定可．`tests/fixtures/**`
                       のような prefix 形式で，相対パス・絶対パス（runner workspace 配下）
                       両方の findings を除外する

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
    - --ignore-glob は dogfooding（自リポジトリへの caller-style 適用）で
      tests/fixtures/ のような lint 対象外 path を summary 件数から外すための
      逃げ道．reviewdog の inline コメント側はこの input の影響を受けない
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Sequence


_MARKDOWNLINT_LINE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::\d+)?\s+(?P<rule>\S+/\S+)(?:\s+(?P<message>.*))?$"
)


def _path_matches_ignore(path: str, pattern: str) -> bool:
    """path が pattern にマッチするか判定する．

    pattern が `<prefix>/**` 形式のとき：

    - path が prefix 自身または `prefix/...` 形式（相対）→ 一致
    - path が `.../prefix/...` または末尾が `/prefix` → 一致．absolute 経路や
      runner workspace 配下の絶対パスもこの分岐で吸収する

    それ以外の pattern は fnmatchcase で評価する．
    """
    norm = path.replace("\\", "/")
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        # 相対 path：prefix 自身または `prefix/...` 形式．
        if norm == prefix or norm.startswith(prefix + "/"):
            return True
        # 絶対 path や runner workspace 配下：path の途中に prefix が
        # ディレクトリ境界として現れる形を吸収する．
        if "/" + prefix + "/" in norm:
            return True
        return False
    return fnmatch.fnmatchcase(norm, pattern)


def _is_ignored(path: str, ignore_globs: Sequence[str] | None) -> bool:
    if not ignore_globs:
        return False
    return any(_path_matches_ignore(path, p) for p in ignore_globs)


def count_textlint(path: Path, ignore_globs: Sequence[str] | None = None) -> dict:
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
        if _is_ignored(file_name, ignore_globs):
            continue
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


def count_markdownlint(path: Path, ignore_globs: Sequence[str] | None = None) -> dict:
    """markdownlint-cli2 のテキストレポートから件数と findings 一覧を返す．"""
    if not Path(path).is_file():
        return {"total": 0, "findings": []}

    findings: list[dict] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = _MARKDOWNLINT_LINE.match(line.rstrip("\r\n"))
            if not m:
                continue
            file_name = m.group("file")
            if _is_ignored(file_name, ignore_globs):
                continue
            try:
                line_no = int(m.group("line"))
            except ValueError:
                line_no = 0
            findings.append(
                {
                    "file": file_name,
                    "line": line_no,
                    "rule": m.group("rule"),
                    "message": (m.group("message") or "").strip(),
                }
            )
    return {"total": len(findings), "findings": findings}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="count-lint-findings.py", add_help=True)
    parser.add_argument("textlint_xml")
    parser.add_argument("markdownlint_txt")
    parser.add_argument(
        "--ignore-glob",
        action="append",
        default=[],
        metavar="PATTERN",
        help="path glob to exclude from findings; repeatable",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv))
    ignore_globs = args.ignore_glob or []

    payload = {
        "markdownlint": count_markdownlint(Path(args.markdownlint_txt), ignore_globs),
        "textlint": count_textlint(Path(args.textlint_xml), ignore_globs),
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
