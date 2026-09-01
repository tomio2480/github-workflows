#!/usr/bin/env python3
"""count-lint-findings.py の JSON を push 前ローカル lint 用の表示へ整える．

bin/lint-md.sh から呼ばれる（Issue #134）．CI は同じ JSON を PR コメントの
summary へ流す．ローカルは端末で読むため，件数と findings 一覧だけを出す．

集計そのものは count-lint-findings.py が担う．そちらは CI の summary でも
使われており，差分ファイルへの絞り込み（--diff-files-from）も含めて検証済み
である．ローカル専用の集計を別に書くと CI と結果がずれるため，表示だけを
本スクリプトへ分ける．

usage:
    count-lint-findings.py ... | render-local-lint-report.py

入力（stdin，JSON）:
    count-lint-findings.py の出力

出力（stdout）:
    linter ごとの件数と `path:line rule message` 形式の findings

終了コード:
    0  指摘なし
    1  指摘あり
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO


def _shorten(path: str) -> str:
    """workspace 配下の絶対パスを相対パスへ戻す．

    textlint の checkstyle 出力はファイル名を絶対パスで書く．端末では長く，
    どのファイルの指摘か読み取りにくい．count-lint-findings.py の絞り込みと
    同じ規則（`GITHUB_WORKSPACE` を prefix として剥がす）で短くする．
    workspace 外のパスはそのまま残す．
    """
    normalized = str(path).replace("\\", "/")
    workspace = (os.environ.get("GITHUB_WORKSPACE") or "").replace("\\", "/").rstrip("/")
    if workspace and normalized.startswith(workspace + "/"):
        return normalized[len(workspace) + 1:]
    return normalized


def _render_section(out: TextIO, title: str, section: dict[str, Any]) -> None:
    findings = section.get("findings") or []
    out.write(f"{title}: {section.get('total', len(findings))} 件\n")
    for finding in findings:
        location = f"{_shorten(finding.get('file'))}:{finding.get('line')}"
        severity = finding.get("severity")
        label = f"[{severity}] " if severity else ""
        out.write(
            f"  {location}  {label}{finding.get('rule')}  {finding.get('message')}\n"
        )


def main(stream: TextIO, out: TextIO) -> int:
    try:
        payload = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON from count-lint-findings.py: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("count-lint-findings.py must produce a JSON object")

    mdlint = payload.get("markdownlint") or {}
    textlint = payload.get("textlint") or {}
    total = int(mdlint.get("total", 0)) + int(textlint.get("total", 0))

    if total == 0:
        out.write("指摘なし\n")
        return 0

    _render_section(out, "markdownlint", mdlint)
    _render_section(out, "textlint", textlint)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.stdin, sys.stdout))
