#!/usr/bin/env python3
"""textlint と markdownlint の検査結果から件数と findings 一覧を集計し JSON を stdout に出す．

composite action の summary 投稿ステップで呼ばれる．集計と投稿の責務分離のため
本スクリプトは「読んで数えて JSON にする」 までを担当し，PR コメント投稿は別の
post-lint-summary.sh が担当する．

usage:
    count-lint-findings.py <textlint-xml> <markdownlint-txt> [--ignore-glob PATTERN ...]
        [--diff-files-from FILE]

入力:
    <textlint-xml>     textlint の checkstyle 形式レポート
    <markdownlint-txt> markdownlint-cli2 の stderr 取り込みテキスト
    --ignore-glob      集計から除外する path glob．繰り返し指定可．`tests/fixtures/**`
                       のような prefix 形式で，相対パス・絶対パス（runner workspace 配下）
                       両方の findings を除外する
    --diff-files-from  PR 差分ファイル一覧（改行区切り）を書いたファイルパス．指定時は
                       一覧外のファイルの findings を summary から除外する（Issue #59:
                       reviewdog の filter-mode はリポジトリ全体走査の結果を絞り込まない
                       ため，summary だけが diff 外まで報告していた事象への対応）．
                       未指定時は従来どおりリポジトリ全体を対象にする

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


def _path_matches_ignore(norm_path: str, pattern: str) -> bool:
    """事前に正規化済みの path が pattern にマッチするか判定する．

    pattern が `<prefix>/**` 形式のとき：

    - path が prefix 自身または `prefix/...` 形式（相対）→ 一致
    - path が `.../prefix/...` 形式または末尾が `/prefix` → 一致．
      runner workspace 配下の絶対 path や directory 自身を指す path も
      この分岐で吸収する

    それ以外の pattern は `fnmatchcase` に委ねる．
    """
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        # 相対 path：prefix 自身または `prefix/...` 形式．
        if norm_path == prefix or norm_path.startswith(prefix + "/"):
            return True
        # 絶対 path や subpath 一致：途中に `/<prefix>/` を含む，
        # または末尾が `/<prefix>` の形（後者は directory 自身を指すケース）．
        if "/" + prefix + "/" in norm_path or norm_path.endswith("/" + prefix):
            return True
        return False
    return fnmatch.fnmatchcase(norm_path, pattern)


def _is_ignored(path: str, ignore_globs: Sequence[str] | None) -> bool:
    if not ignore_globs:
        return False
    # path 正規化はループ外で 1 回だけ実施する．pattern 数が多い場合の
    # 無駄な replace を避ける．
    norm_path = path.replace("\\", "/")
    return any(_path_matches_ignore(norm_path, p) for p in ignore_globs)


def _is_in_diff_scope(path: str, diff_files: Sequence[str] | None) -> bool:
    """diff_files が None なら絞り込みなし（全 in-scope）．

    リストが渡された場合（空リスト含む）は，各要素を `<file>/**` 相当の
    prefix パターンとみなして `_path_matches_ignore` を再利用し，一致した
    ものだけ in-scope とする．一致判定は ignore-glob と対称にすることで
    絶対パス・相対パス両対応の挙動を揃える．
    """
    if diff_files is None:
        return True
    # diff_files は呼び出し元（main()）で正規化済みの前提とする．
    # ignore_globs / _is_ignored と同じ規約（要素側はループ内で再正規化しない）．
    norm_path = path.replace("\\", "/")
    for f in diff_files:
        if norm_path == f or _path_matches_ignore(norm_path, f + "/**"):
            return True
    return False


def count_textlint(
    path: Path,
    ignore_globs: Sequence[str] | None = None,
    diff_files: Sequence[str] | None = None,
) -> dict:
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
        if not _is_in_diff_scope(file_name, diff_files):
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


def count_markdownlint(
    path: Path,
    ignore_globs: Sequence[str] | None = None,
    diff_files: Sequence[str] | None = None,
) -> dict:
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
            if not _is_in_diff_scope(file_name, diff_files):
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
    parser.add_argument(
        "--diff-files-from",
        metavar="FILE",
        help=(
            "newline-separated list of PR diff files (relative paths); "
            "when given, findings outside this list are excluded from the "
            "summary. Omit to keep the legacy repo-wide scope (Issue #59)"
        ),
    )
    return parser


def main(argv: Sequence[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv))

    # ignore_globs は早期に正規化して fail-fast．空文字や空白のみの値は
    # caller の設定ミスを示すため silent に通さず ValueError で落とす．
    ignore_globs: list[str] = []
    for p in args.ignore_glob or []:
        normalized = p.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("--ignore-glob must not be empty or whitespace only")
        ignore_globs.append(normalized)

    # --diff-files-from 未指定なら None（絞り込みなし = 従来挙動）．
    # 指定されたファイルの空行は無視する．
    diff_files: list[str] | None = None
    if args.diff_files_from:
        diff_files = [
            line.strip().replace("\\", "/")
            for line in Path(args.diff_files_from).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    payload = {
        "markdownlint": count_markdownlint(
            Path(args.markdownlint_txt), ignore_globs, diff_files
        ),
        "textlint": count_textlint(Path(args.textlint_xml), ignore_globs, diff_files),
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
