#!/usr/bin/env python3
"""checkstyle レポートの絶対パスが workspace 配下に収まることを確かめる．

textlint は checkstyle 出力へファイル名を絶対パスで書く．集計側の
`count-lint-findings.py` は `GITHUB_WORKSPACE` を prefix として剥がし，
リポジトリルート相対へ戻してから対象一覧と突き合わせる．

剥がせなかった絶対パスは対象一覧と一致せず，その指摘は黙って捨てられる．
lint 自体は成功しているため，利用者には「指摘なし」として 0 終了で見える．
Windows では大小文字・8.3 名・ジャンクションの解決有無で表記が割れうるため，
prefix 比較は落ちる余地がある（Issue #169 のレビュー指摘）．

本スクリプトはその沈黙を止める．剥がせない絶対パスが 1 件でもあれば，
該当パスを標準エラーへ並べて非 0 で終わる．
判定は `count-lint-findings.py` の `_strip_workspace_prefix` と同じ規則で行う．
緩めると「検査したつもり」になるため，あえて同じ厳しさに揃える．

引数は 2 つ（checkstyle XML・workspace のパス）．
レポートが無い場合は 0 で終わる．lint が 1 件も出力しない経路があるためである．
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Sequence

# ドライブレター始まり（`C:/...`）と POSIX の絶対パス（`/...`）を絶対とみなす．
_DRIVE_PREFIX_LENGTH = 2


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def is_absolute(path: str) -> bool:
    if path.startswith("/"):
        return True
    return (
        len(path) > _DRIVE_PREFIX_LENGTH
        and path[1] == ":"
        and path[0].isalpha()
        and path[_DRIVE_PREFIX_LENGTH] == "/"
    )


def unmapped_paths(report: Path, workspace: str) -> list[str]:
    """workspace prefix を剥がせない絶対パスを返す．"""
    if not report.is_file():
        return []
    try:
        tree = ET.parse(report)
    except ET.ParseError as e:
        raise ValueError(f"failed to parse the checkstyle report: {report}") from e

    prefix = _normalize(workspace).rstrip("/")
    unmapped: list[str] = []
    for file_el in tree.getroot().iter("file"):
        name = file_el.get("name") or ""
        if not name:
            continue
        normalized = _normalize(name)
        if not is_absolute(normalized):
            continue
        if prefix and normalized.startswith(prefix + "/"):
            continue
        unmapped.append(name)
    return unmapped


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print("usage: check-report-paths.py <report> <workspace>", file=sys.stderr)
        return 2

    try:
        unmapped = unmapped_paths(Path(argv[0]), argv[1])
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    if not unmapped:
        return 0

    print(
        "lint report paths cannot be mapped back to the repository; "
        f"findings would be dropped silently (workspace={argv[1]}):",
        file=sys.stderr,
    )
    for path in unmapped:
        print(f"  {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
