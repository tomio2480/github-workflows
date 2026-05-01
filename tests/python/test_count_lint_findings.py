"""scripts/count-lint-findings.py の単体テスト．

仕様:
    - textlint の checkstyle XML を読み severity 別の件数を集計する
      ・空 XML → {"error": 0, "warning": 0, "info": 0, "total": 0}
      ・severity 混在 → 内訳を正しく集計
      ・存在しないファイルパス → 全 0（fail-open．composite action 経路で
        XML 生成前に呼ばれた場合の防御）
      ・XML が parse 不能 → ValueError
    - markdownlint-cli2 の stderr 取り込みテキストを読み件数を集計する
      ・空文字／banner のみ → 0
      ・finding 行（path:line[:col] RULE/... の形）の数を返す
      ・存在しないファイルパス → 0
    - main(argv) は textlint_xml と markdownlint_txt の 2 引数を受け
      stdout に JSON を書く．argv が 2 でないときは ValueError．
"""

from __future__ import annotations

import importlib
import io
import json
from pathlib import Path

import pytest


_MODULE = importlib.import_module("count-lint-findings")
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---- count_textlint -------------------------------------------------------

def test_count_textlint_empty_xml_returns_zeros():
    result = _MODULE.count_textlint(_FIXTURES / "textlint-reports" / "empty.xml")
    assert result == {"error": 0, "warning": 0, "info": 0, "total": 0}


def test_count_textlint_mixed_severities():
    result = _MODULE.count_textlint(_FIXTURES / "textlint-reports" / "mixed.xml")
    assert result == {"error": 1, "warning": 3, "info": 1, "total": 5}


def test_count_textlint_missing_file_returns_zeros(tmp_path):
    result = _MODULE.count_textlint(tmp_path / "does-not-exist.xml")
    assert result == {"error": 0, "warning": 0, "info": 0, "total": 0}


def test_count_textlint_malformed_xml_raises(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<not-xml", encoding="utf-8")
    with pytest.raises(ValueError):
        _MODULE.count_textlint(bad)


# ---- count_markdownlint ---------------------------------------------------

def test_count_markdownlint_empty_returns_zero():
    result = _MODULE.count_markdownlint(
        _FIXTURES / "markdownlint-reports" / "empty.txt"
    )
    assert result == {"total": 0}


def test_count_markdownlint_with_issues_counts_findings():
    result = _MODULE.count_markdownlint(
        _FIXTURES / "markdownlint-reports" / "with-issues.txt"
    )
    assert result == {"total": 3}


def test_count_markdownlint_missing_file_returns_zero(tmp_path):
    result = _MODULE.count_markdownlint(tmp_path / "does-not-exist.txt")
    assert result == {"total": 0}


def test_count_markdownlint_ignores_banner_only_lines(tmp_path):
    # banner だけで finding 行が無いケース
    txt = tmp_path / "banner-only.txt"
    txt.write_text(
        "markdownlint-cli2 v0.13.0\n"
        "Finding: README.md\n"
        "Linting: 1 file(s)\n"
        "Summary: 0 error(s)\n",
        encoding="utf-8",
    )
    assert _MODULE.count_markdownlint(txt) == {"total": 0}


def test_count_markdownlint_handles_path_without_column(tmp_path):
    txt = tmp_path / "no-col.txt"
    txt.write_text(
        "docs/sample.md:7 MD047/single-trailing-newline Files should end with a single newline character\n",
        encoding="utf-8",
    )
    assert _MODULE.count_markdownlint(txt) == {"total": 1}


# ---- main ------------------------------------------------------------------

def test_main_emits_combined_json(capsys):
    rc = _MODULE.main(
        [
            str(_FIXTURES / "textlint-reports" / "mixed.xml"),
            str(_FIXTURES / "markdownlint-reports" / "with-issues.txt"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "markdownlint": {"total": 3},
        "textlint": {"error": 1, "warning": 3, "info": 1, "total": 5},
    }


def test_main_with_missing_files_returns_zero_totals(capsys, tmp_path):
    rc = _MODULE.main(
        [
            str(tmp_path / "missing.xml"),
            str(tmp_path / "missing.txt"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "markdownlint": {"total": 0},
        "textlint": {"error": 0, "warning": 0, "info": 0, "total": 0},
    }


def test_main_wrong_argv_raises_value_error():
    with pytest.raises(ValueError):
        _MODULE.main(["only-one"])
