"""scripts/render-local-lint-report.py の単体テスト．

仕様:
    - count-lint-findings.py の JSON を stdin から読み，人が読める形へ整える
    - findings は `path:line rule message` の 1 行で出す
    - markdownlint と textlint を見出しで分け，件数を添える
    - textlint の findings には severity を添える
    - 指摘 0 件のときは「指摘なし」の 1 行だけを出す
    - main(stream) は指摘があれば 1，無ければ 0 を返す（呼び出し側の終了コード）
    - JSON が壊れているときは ValueError（黙って 0 件と誤読させない）
"""

from __future__ import annotations

import importlib
import io
import json

import pytest


_MODULE = importlib.import_module("render-local-lint-report")


def _payload(mdlint=None, textlint=None):
    return {
        "diff_scoped": True,
        "markdownlint": {
            "total": len(mdlint or []),
            "repo_total": len(mdlint or []),
            "findings": mdlint or [],
        },
        "textlint": {
            "error": 0,
            "warning": 0,
            "info": 0,
            "total": len(textlint or []),
            "repo_total": len(textlint or []),
            "findings": textlint or [],
        },
    }


def _run(payload):
    stream = io.StringIO(json.dumps(payload))
    out = io.StringIO()
    status = _MODULE.main(stream, out)
    return status, out.getvalue()


def test_reports_no_findings_and_returns_zero():
    status, out = _run(_payload())

    assert status == 0
    assert "指摘なし" in out


def test_returns_one_when_markdownlint_has_findings():
    status, out = _run(
        _payload(
            mdlint=[
                {
                    "file": "docs/a.md",
                    "line": 12,
                    "rule": "MD012/no-multiple-blanks",
                    "message": "Multiple consecutive blank lines",
                }
            ]
        )
    )

    assert status == 1
    assert "docs/a.md:12" in out
    assert "MD012/no-multiple-blanks" in out
    assert "Multiple consecutive blank lines" in out


def test_returns_one_when_textlint_has_findings():
    status, out = _run(
        _payload(
            textlint=[
                {
                    "file": "docs/b.md",
                    "line": 3,
                    "severity": "error",
                    "rule": "ja-technical-writing/sentence-length",
                    "message": "Line 3 sentence length(90) exceeds the maximum(80)",
                }
            ]
        )
    )

    assert status == 1
    assert "docs/b.md:3" in out
    assert "error" in out
    assert "ja-technical-writing/sentence-length" in out


def test_shows_a_count_for_each_linter():
    status, out = _run(
        _payload(
            mdlint=[
                {"file": "a.md", "line": 1, "rule": "MD001", "message": "x"},
                {"file": "a.md", "line": 2, "rule": "MD002", "message": "y"},
            ]
        )
    )

    assert status == 1
    assert "markdownlint: 2" in out
    assert "textlint: 0" in out


def test_lists_every_finding():
    status, out = _run(
        _payload(
            mdlint=[
                {"file": "a.md", "line": 1, "rule": "MD001", "message": "x"},
                {"file": "b.md", "line": 2, "rule": "MD002", "message": "y"},
            ]
        )
    )

    assert status == 1
    assert "a.md:1" in out
    assert "b.md:2" in out


def test_shortens_absolute_paths_under_the_workspace(monkeypatch):
    # textlint の checkstyle 出力は絶対パスを書く．端末では長すぎて読めない．
    monkeypatch.setenv("GITHUB_WORKSPACE", "C:/repo")
    status, out = _run(
        _payload(
            textlint=[
                {
                    "file": "C:\\repo\\docs\\b.md",
                    "line": 3,
                    "severity": "error",
                    "rule": "prh",
                    "message": "x",
                }
            ]
        )
    )

    assert status == 1
    assert "docs/b.md:3" in out
    assert "C:/repo" not in out


def test_keeps_paths_outside_the_workspace_as_is(monkeypatch):
    monkeypatch.setenv("GITHUB_WORKSPACE", "C:/repo")
    status, out = _run(
        _payload(
            mdlint=[
                {"file": "/other/a.md", "line": 1, "rule": "MD001", "message": "x"}
            ]
        )
    )

    assert status == 1
    assert "/other/a.md:1" in out


def test_raises_on_broken_json():
    with pytest.raises(ValueError):
        _MODULE.main(io.StringIO("not json"), io.StringIO())
