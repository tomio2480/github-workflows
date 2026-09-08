#!/usr/bin/env python3
"""共通の集計結果をローカル lint 用に表示する（docs/local-lint.md）．

引数なしでは count-lint-findings.py の JSON を stdin から受け，全文を表示する．
指摘なしは exit 0，指摘ありは exit 1．--record-dir 指定時は保存済み集計から
要約と JSON を生成する．記録成功は exit 0，失敗は exit 2 とし，元の lint の
終了コードは呼び出し元の bin/lint-md.sh が保持する．
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
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


def record_run(
    directory: Path, *, exit_code: int, root: str, head_sha: str,
    source_root: str, source_sha: str, selected: int, mirrored: int, limit: int,
) -> dict[str, Any]:
    """集計済みの全文を残し，表示する指摘だけを制限する．"""
    if limit < 0 or exit_code not in (0, 1, 2):
        raise ValueError("invalid limit or exit code")
    directory = Path(directory).resolve()
    status = "error" if exit_code == 2 else "findings" if exit_code == 1 else "ok"
    findings = None
    total = None
    if exit_code != 2:
        findings = []
        total = 0
        if selected == 0 or mirrored == 0:
            if exit_code != 0:
                raise ValueError("findings without lint targets")
            status = "not_applicable"
        else:
            try:
                payload = json.loads((directory / "findings.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("missing or invalid lint aggregation") from exc
            for name in ("markdownlint", "textlint"):
                section = payload[name]
                items = section["findings"]
                if section["total"] != len(items):
                    raise ValueError("inconsistent lint aggregation")
                total += len(items)
                for item in items[:max(0, limit - len(findings))]:
                    message = " ".join(str(item.get("message", "")).split())
                    findings.append({
                        "linter": name, "file": _shorten(item.get("file", "")),
                        "line": item.get("line"), "rule": item.get("rule"),
                        "severity": item.get("severity"),
                        "message": message[:240] + ("…" if len(message) > 240 else ""),
                        "message_truncated": len(message) > 240,
                    })
            if (total > 0) != (exit_code == 1):
                raise ValueError("lint aggregation does not match exit code")

    artifacts = {
        key: str(directory / filename)
        for key, filename in {
            "full": "full.txt", "diagnostics": "diagnostics.log",
            "targets": "targets.txt", "findings": "findings.json",
            "markdownlint": "markdownlint-report.txt", "textlint": "textlint-report.xml",
            "textlint_stderr": "textlint-stderr.log", "install": "install.log",
        }.items() if (directory / filename).is_file()
    }
    artifacts.update(summary=str(directory / "summary.txt"), report=str(directory / "report.json"))
    returned = len(findings) if findings is not None else None
    report = {
        "schema_version": 1, "tool": "lint-md", "status": status, "exit_code": exit_code,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "root": root, "head_sha": head_sha, "source_root": source_root, "source_sha": source_sha,
        "coverage": {"selected": selected if selected >= 0 else None,
                     "mirrored": mirrored if mirrored >= 0 else None},
        "display": {"total": total, "returned": returned,
                    "omitted": total - returned if total is not None else None},
        "findings": findings, "artifacts": artifacts,
    }
    lines = [f"lint-md: {status} (exit {exit_code})",
             f"scope: selected={report['coverage']['selected']}, mirrored={report['coverage']['mirrored']}",
             f"findings: total={total}, returned={returned}, omitted={report['display']['omitted']}"]
    for item in findings or []:
        lines.append(f"  {item['file']}:{item['line']} {item['rule']} {item['message']}")
    lines.extend(f"{key}: {artifacts[key]}" for key in ("full", "diagnostics", "report") if key in artifacts)
    (directory / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return report


def cli() -> int:
    if len(sys.argv) == 1:
        return main(sys.stdin, sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-dir", type=Path, required=True)
    parser.add_argument("--format", choices=("full", "summary", "json"), required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--selected", type=int, required=True)
    parser.add_argument("--mirrored", type=int, required=True)
    parser.add_argument("--limit", type=int, required=True)
    args = vars(parser.parse_args())
    directory = args.pop("record_dir")
    output_format = args.pop("format")
    try:
        record_run(directory, **args)
        filename = {"full": "full.txt", "summary": "summary.txt", "json": "report.json"}[output_format]
        # 全文も一括でメモリへ載せず，保存した順序のまま再生する．
        with (directory / filename).open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                sys.stdout.write(line)
        if output_format == "full":
            with (directory / "diagnostics.log").open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    sys.stderr.write(line)
            print(f"lint-md: saved run: {directory}", file=sys.stderr)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"lint-md: cannot record run at {directory}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(cli())
