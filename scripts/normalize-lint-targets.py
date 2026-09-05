#!/usr/bin/env python3
"""lint 対象を LF 正規化した複製として書き出す（Issue #169）．

CRLF の作業ツリーでは textlint が行末の CR を文の字数へ数える．文が行を
またぐとき CR がその文の内側に入り，80 字ちょうどの文が 81 字と報告される．
CI は LF の checkout で走るため，同じ commit でも件数が食い違う．
作業ツリーの改行設定は利用者の環境に属するため書き換えず，複製の側で lint する．

変換するのは `\\r\\n` の組だけである．単独の `\\r` は改行ではなく，消すと行が
連結されて指摘が消えたり増えたりする．末尾改行も足さない．markdownlint の
MD047 が末尾改行の有無を見るためである．

引数は 3 つ（対象一覧・複製元のルート・複製先のルート）．
対象一覧はリポジトリルート相対のパスを 1 行 1 件で並べたものとする．
実体の無い行は飛ばす．差分には削除済みファイルも入り，glob も拾わないためである．
標準出力へ複製した件数を書く．
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath
from typing import Sequence


def _is_inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def normalize(data: bytes) -> bytes:
    """CRLF だけを LF へ寄せる．単独の CR は残す．"""
    return data.replace(b"\r\n", b"\n")


def main(argv: Sequence[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: normalize-lint-targets.py <targets> <src-root> <dest-root>",
            file=sys.stderr,
        )
        return 2

    targets_path, src_root, dest_root = (Path(a) for a in argv)
    src_root = src_root.resolve()
    dest_root = dest_root.resolve()

    copied = 0
    for line in targets_path.read_text(encoding="utf-8").splitlines():
        # 先頭の空白はファイル名の一部でありうる．strip しない．
        if not line:
            continue
        # 対象一覧はリポジトリルート相対である．外へ出る指定は受け取らない．
        if PurePosixPath(line).is_absolute() or ".." in PurePosixPath(line).parts:
            print(f"target points outside the repository: {line}", file=sys.stderr)
            return 1
        source = src_root / line
        if not source.is_file():
            continue
        destination = dest_root / line
        if not _is_inside(dest_root, destination.resolve().parent):
            print(f"target points outside the copy root: {line}", file=sys.stderr)
            return 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(normalize(source.read_bytes()))
        copied += 1

    print(copied)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
