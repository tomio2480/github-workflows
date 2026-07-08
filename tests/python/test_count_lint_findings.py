"""scripts/count-lint-findings.py の単体テスト．

仕様:
    - textlint の checkstyle XML を読み severity 別の件数と findings 一覧を返す
      ・空 XML → counts 0 / findings []
      ・severity 混在 → 内訳・順序・ファイル名・rule 名を保持
      ・存在しないファイル → 全 0（fail-open．composite action 経路で XML 生成
        前に呼ばれた場合の防御）
      ・XML が parse 不能 → ValueError
    - markdownlint-cli2 の stderr 取り込みテキストを読み件数と findings 一覧を返す
      ・空文字／banner のみ → 0
      ・finding 行（path:line[:col] RULE/... の形）の数と内容を返す
      ・path が非貪欲（non-greedy）にマッチし，ファイル名にコロンが含まれる場合も
        左端のセグメントを正しく拾う
      ・存在しないファイル → 0
    - main(argv) は textlint_xml と markdownlint_txt の 2 引数を受け
      stdout に JSON を書く．argv が 2 でないときは ValueError．
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


_MODULE = importlib.import_module("count-lint-findings")
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


# ---- count_textlint -------------------------------------------------------

def test_count_textlint_empty_xml_returns_zero_counts_and_empty_findings():
    result = _MODULE.count_textlint(_FIXTURES / "textlint-reports" / "empty.xml")
    assert result == {
        "error": 0,
        "warning": 0,
        "info": 0,
        "total": 0,
        "findings": [],
    }


def test_count_textlint_mixed_severities_returns_counts_and_findings():
    result = _MODULE.count_textlint(_FIXTURES / "textlint-reports" / "mixed.xml")
    assert result["error"] == 1
    assert result["warning"] == 3
    assert result["info"] == 1
    assert result["total"] == 5
    findings = result["findings"]
    assert len(findings) == 5
    # 1 つ目を spot-check：file 名・line・severity・rule・message が拾えている
    assert findings[0] == {
        "file": "docs/sample.md",
        "line": 3,
        "severity": "error",
        "rule": "rule-a",
        "message": "something broken",
    }
    # 別ファイルの finding も含まれる
    assert findings[-1]["file"] == "docs/other.md"
    assert findings[-1]["severity"] == "warning"


def test_count_textlint_missing_file_returns_zero_counts_and_empty_findings(tmp_path):
    result = _MODULE.count_textlint(tmp_path / "does-not-exist.xml")
    assert result == {
        "error": 0,
        "warning": 0,
        "info": 0,
        "total": 0,
        "findings": [],
    }


def test_count_textlint_malformed_xml_raises(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<not-xml", encoding="utf-8")
    with pytest.raises(ValueError):
        _MODULE.count_textlint(bad)


def test_count_textlint_ignore_globs_excludes_matching_findings():
    # tests/fixtures/** に該当する 3 件（warning 2 + info 1）を除外し
    # docs/keep.md の 1 件（error）のみ残ること．severity 内訳と総件数も整合．
    result = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        ignore_globs=["tests/fixtures/**"],
    )
    assert result["error"] == 1
    assert result["warning"] == 0
    assert result["info"] == 0
    assert result["total"] == 1
    assert len(result["findings"]) == 1
    assert result["findings"][0]["file"] == "docs/keep.md"


def test_count_textlint_ignore_globs_matches_absolute_paths_via_subpath():
    # 絶対パス（runner workspace）も `tests/fixtures/**` で除外できる．
    result = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        ignore_globs=["tests/fixtures/**"],
    )
    files = [f["file"] for f in result["findings"]]
    assert "/home/runner/work/repo/repo/tests/fixtures/markdown/another.md" not in files
    assert "tests/fixtures/markdown/with-issues.md" not in files


def test_count_textlint_multiple_ignore_globs_or_combined(tmp_path):
    xml = tmp_path / "multi.xml"
    xml.write_text(
        '<?xml version="1.0"?><checkstyle><file name="a/x.md">'
        '<error line="1" severity="error" message="m" source="r"/></file>'
        '<file name="b/y.md">'
        '<error line="1" severity="error" message="m" source="r"/></file>'
        '<file name="c/z.md">'
        '<error line="1" severity="error" message="m" source="r"/></file>'
        "</checkstyle>",
        encoding="utf-8",
    )
    result = _MODULE.count_textlint(xml, ignore_globs=["a/**", "b/**"])
    assert result["total"] == 1
    assert result["findings"][0]["file"] == "c/z.md"


def test_count_textlint_empty_ignore_globs_keeps_all_findings():
    full = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml"
    )
    no_op = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        ignore_globs=[],
    )
    assert full == no_op


# ---- count_markdownlint ---------------------------------------------------

def test_count_markdownlint_empty_returns_zero_total_and_empty_findings():
    result = _MODULE.count_markdownlint(
        _FIXTURES / "markdownlint-reports" / "empty.txt"
    )
    assert result == {"total": 0, "findings": []}


def test_count_markdownlint_with_issues_counts_findings_and_extracts_metadata():
    result = _MODULE.count_markdownlint(
        _FIXTURES / "markdownlint-reports" / "with-issues.txt"
    )
    assert result["total"] == 3
    findings = result["findings"]
    assert len(findings) == 3
    # 先頭の finding：MD041 first-line-heading
    assert findings[0]["file"] == "tests/fixtures/markdown/with-issues.md"
    assert findings[0]["line"] == 1
    assert findings[0]["rule"].startswith("MD041/")
    assert "First line in a file should be a top-level heading" in findings[0]["message"]
    # 末尾の finding（column が無い形）：MD047
    assert findings[-1]["line"] == 7
    assert findings[-1]["rule"].startswith("MD047/")


def test_count_markdownlint_missing_file_returns_zero(tmp_path):
    result = _MODULE.count_markdownlint(tmp_path / "does-not-exist.txt")
    assert result == {"total": 0, "findings": []}


def test_count_markdownlint_ignores_banner_only_lines(tmp_path):
    txt = tmp_path / "banner-only.txt"
    txt.write_text(
        "markdownlint-cli2 v0.13.0\n"
        "Finding: README.md\n"
        "Linting: 1 file(s)\n"
        "Summary: 0 error(s)\n",
        encoding="utf-8",
    )
    assert _MODULE.count_markdownlint(txt) == {"total": 0, "findings": []}


def test_count_markdownlint_handles_path_without_column(tmp_path):
    txt = tmp_path / "no-col.txt"
    txt.write_text(
        "docs/sample.md:7 MD047/single-trailing-newline Files should end with a single newline character\n",
        encoding="utf-8",
    )
    result = _MODULE.count_markdownlint(txt)
    assert result["total"] == 1
    assert result["findings"][0]["line"] == 7


def test_count_markdownlint_ignore_globs_excludes_matching(tmp_path):
    result = _MODULE.count_markdownlint(
        _FIXTURES / "markdownlint-reports" / "with-ignored-paths.txt",
        ignore_globs=["tests/fixtures/**"],
    )
    # 4 件中 3 件が tests/fixtures/ 配下（うち 1 件は絶対パス）．残るのは docs/keep.md の 1 件．
    assert result["total"] == 1
    assert result["findings"][0]["file"] == "docs/keep.md"


def test_count_markdownlint_path_with_colon_uses_non_greedy_match(tmp_path):
    # ファイル名にコロンを含む（Windows のドライブ表記等を模した）入力でも
    # 行番号として正しい左側の数値を拾えること．greedy だと path を末尾近くまで
    # 飲み込み「最後のコロン以降の数値」 が line になってしまう（例えば
    # `docs/sample:colon.md:12:5 ...` で line=5 と誤検出）．非貪欲なら最初に
    # 続けて数値が来るコロンで止まるため line=12（textlint と同義の本来の
    # 行番号）になる．
    txt = tmp_path / "weird-path.txt"
    txt.write_text(
        "docs/sample:colon.md:12:5 MD012/no-multiple-blanks Multiple consecutive blank lines\n",
        encoding="utf-8",
    )
    result = _MODULE.count_markdownlint(txt)
    assert result["total"] == 1
    assert result["findings"][0]["file"] == "docs/sample:colon.md"
    assert result["findings"][0]["line"] == 12


# ---- main ------------------------------------------------------------------

def test_main_emits_combined_json_with_findings(capsys):
    rc = _MODULE.main(
        [
            str(_FIXTURES / "textlint-reports" / "mixed.xml"),
            str(_FIXTURES / "markdownlint-reports" / "with-issues.txt"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["markdownlint"]["total"] == 3
    assert len(payload["markdownlint"]["findings"]) == 3
    assert payload["textlint"]["total"] == 5
    assert payload["textlint"]["error"] == 1
    assert payload["textlint"]["warning"] == 3
    assert payload["textlint"]["info"] == 1
    assert len(payload["textlint"]["findings"]) == 5


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
        "markdownlint": {"total": 0, "findings": []},
        "textlint": {"error": 0, "warning": 0, "info": 0, "total": 0, "findings": []},
    }


def test_main_wrong_argv_raises_value_error():
    # argparse は不足引数で SystemExit(2) を投げる．exit code を厳密に検査することで
    # 「黙って exit 0」 のような誤動作を回避する．
    with pytest.raises(SystemExit) as exc:
        _MODULE.main(["only-one"])
    assert exc.value.code == 2


def test_main_rejects_empty_or_whitespace_ignore_glob():
    # 空文字 / 空白のみは設定ミスの可能性が高いため fail-fast で ValueError．
    for bad in ("", "   ", "\t"):
        with pytest.raises(ValueError, match="ignore-glob"):
            _MODULE.main(
                [
                    str(_FIXTURES / "textlint-reports" / "empty.xml"),
                    str(_FIXTURES / "markdownlint-reports" / "empty.txt"),
                    "--ignore-glob",
                    bad,
                ]
            )


def test_main_accepts_repeated_ignore_glob(capsys):
    rc = _MODULE.main(
        [
            str(_FIXTURES / "textlint-reports" / "with-ignored-paths.xml"),
            str(_FIXTURES / "markdownlint-reports" / "with-ignored-paths.txt"),
            "--ignore-glob",
            "tests/fixtures/**",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # textlint: docs/keep.md の 1 件のみ
    assert payload["textlint"]["total"] == 1
    assert payload["textlint"]["findings"][0]["file"] == "docs/keep.md"
    # markdownlint: docs/keep.md の 1 件のみ
    assert payload["markdownlint"]["total"] == 1
    assert payload["markdownlint"]["findings"][0]["file"] == "docs/keep.md"


# ---- --diff-files-from (Issue #59: summary を PR 差分ファイルのみに絞る) ----

def test_count_textlint_diff_files_scopes_to_listed_files():
    # with-ignored-paths.xml は docs/keep.md（error 1件）と
    # tests/fixtures/markdown/... 配下（warning 2 + info 1）を含む．
    # diff_files に docs/keep.md のみを渡すと，それ以外は除外される．
    result = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        diff_files=["docs/keep.md"],
    )
    assert result["total"] == 1
    assert result["findings"][0]["file"] == "docs/keep.md"


def test_count_textlint_diff_files_none_keeps_all_findings():
    # diff_files 未指定（None）は従来どおり全 findings を返す．
    full = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml"
    )
    scoped = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        diff_files=None,
    )
    assert full == scoped


def test_count_textlint_diff_files_empty_list_excludes_everything():
    # diff_files=[] は「差分ファイルが 0 件」を意味するため全除外する．
    # None（絞り込みなし）と [] （0 件に絞り込み）は区別する．
    result = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        diff_files=[],
    )
    assert result["total"] == 0
    assert result["findings"] == []


def test_count_textlint_diff_files_matches_absolute_paths_via_workspace_strip(
    monkeypatch,
):
    # with-ignored-paths.xml の 1 件は絶対パス
    # /home/runner/work/repo/repo/tests/fixtures/markdown/another.md．
    # GITHUB_WORKSPACE を設定すれば，その prefix を剥がした相対パスで
    # diff_files と完全一致させられる．
    monkeypatch.setenv("GITHUB_WORKSPACE", "/home/runner/work/repo/repo")
    result = _MODULE.count_textlint(
        _FIXTURES / "textlint-reports" / "with-ignored-paths.xml",
        diff_files=["tests/fixtures/markdown/another.md"],
    )
    files = [f["file"] for f in result["findings"]]
    assert len(files) == 1
    assert files[0] == "/home/runner/work/repo/repo/tests/fixtures/markdown/another.md"


def test_count_textlint_diff_files_rejects_false_positive_suffix_match(tmp_path):
    # 差分ファイルが docs/keep.md のとき，末尾が一致するだけの無関係な
    # sub/docs/keep.md を誤って in-scope にしてはいけない（サフィックス一致
    # による誤判定の回帰防止）．
    xml = tmp_path / "suffix.xml"
    xml.write_text(
        '<?xml version="1.0"?><checkstyle>'
        '<file name="sub/docs/keep.md">'
        '<error line="1" severity="error" message="m" source="r"/></file>'
        "</checkstyle>",
        encoding="utf-8",
    )
    result = _MODULE.count_textlint(xml, diff_files=["docs/keep.md"])
    assert result["total"] == 0
    assert result["findings"] == []


def test_count_markdownlint_diff_files_scopes_to_listed_files():
    result = _MODULE.count_markdownlint(
        _FIXTURES / "markdownlint-reports" / "with-ignored-paths.txt",
        diff_files=["docs/keep.md"],
    )
    assert result["total"] == 1
    assert result["findings"][0]["file"] == "docs/keep.md"


def test_main_accepts_diff_files_from_file(capsys, tmp_path):
    diff_list = tmp_path / "diff-files.txt"
    diff_list.write_text("docs/keep.md\n\n", encoding="utf-8")
    rc = _MODULE.main(
        [
            str(_FIXTURES / "textlint-reports" / "with-ignored-paths.xml"),
            str(_FIXTURES / "markdownlint-reports" / "with-ignored-paths.txt"),
            "--diff-files-from",
            str(diff_list),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["textlint"]["total"] == 1
    assert payload["textlint"]["findings"][0]["file"] == "docs/keep.md"
    assert payload["markdownlint"]["total"] == 1
    assert payload["markdownlint"]["findings"][0]["file"] == "docs/keep.md"


def test_main_without_diff_files_from_keeps_all_findings(capsys):
    # --diff-files-from 未指定時は従来どおりリポジトリ全体の findings を返す
    # （後方互換：既存 caller の挙動を変えない）．
    rc = _MODULE.main(
        [
            str(_FIXTURES / "textlint-reports" / "with-ignored-paths.xml"),
            str(_FIXTURES / "markdownlint-reports" / "with-ignored-paths.txt"),
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["textlint"]["total"] == 4
    assert payload["markdownlint"]["total"] == 4
