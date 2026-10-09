"""Saved local lint runs preserve outcomes while bounding the displayed findings."""

import importlib
import json

import pytest


MODULE = importlib.import_module("render-local-lint-report")


def make_run(tmp_path, count=0):
    directory = tmp_path / "記録 with spaces"
    directory.mkdir()
    findings = [
        {"file": "docs/a.md", "line": i + 1, "rule": "MD001", "message": "長い説明" * 100}
        for i in range(count)
    ]
    payload = {
        "markdownlint": {"total": count, "findings": findings},
        "textlint": {"total": 0, "findings": []},
    }
    (directory / "findings.json").write_text(json.dumps(payload), encoding="utf-8")
    (directory / "full.txt").write_text("complete output\n", encoding="utf-8")
    (directory / "diagnostics.log").write_text("source diagnostic\n", encoding="utf-8")
    return directory


def record(directory, code=0, selected=1, limit=20):
    return MODULE.record_run(
        directory, exit_code=code, root="C:/caller", head_sha="a" * 40,
        source_root="C:/central", source_sha="b" * 40,
        selected=selected, mirrored=selected, limit=limit,
    )


def test_limits_only_the_display_and_preserves_all_findings(tmp_path):
    directory = make_run(tmp_path, 100)
    report = record(directory, code=1, limit=3)

    assert report["status"] == "findings"
    assert report["exit_code"] == 1
    assert report["display"] == {"total": 100, "returned": 3, "omitted": 97}
    assert len(report["findings"]) == 3
    assert len(report["findings"][0]["message"]) <= 241
    assert report["findings"][0]["message_truncated"] is True
    assert len(json.loads((directory / "findings.json").read_text())["markdownlint"]["findings"]) == 100
    assert (directory / "full.txt").read_text() == "complete output\n"
    summary = (directory / "summary.txt").read_text(encoding="utf-8")
    assert "97" in summary
    assert "full.txt" in summary
    assert len(summary) < 2500


@pytest.mark.parametrize("code,selected,expected", [(0, 1, "ok"), (0, 0, "not_applicable"), (2, 1, "error")])
def test_records_outcome_without_turning_failure_into_zero(tmp_path, code, selected, expected):
    directory = make_run(tmp_path)
    if code == 2 or selected == 0:
        (directory / "findings.json").unlink()
    report = record(directory, code=code, selected=selected)

    assert report["status"] == expected
    assert report["exit_code"] == code
    assert report["schema_version"] == 1
    assert report["head_sha"] == "a" * 40
    if code == 2:
        assert report["display"]["total"] is None
        assert report["findings"] is None
    saved = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    assert saved == report


def test_does_not_treat_missing_successful_aggregation_as_clean(tmp_path):
    directory = make_run(tmp_path)
    (directory / "findings.json").unlink()
    with pytest.raises(ValueError):
        record(directory)


def test_display_limit_is_shared_by_both_linters(tmp_path):
    directory = make_run(tmp_path, 2)
    payload = json.loads((directory / "findings.json").read_text(encoding="utf-8"))
    payload["textlint"] = payload["markdownlint"]
    (directory / "findings.json").write_text(json.dumps(payload), encoding="utf-8")
    report = record(directory, code=1, limit=3)
    assert [item["linter"] for item in report["findings"]] == ["markdownlint", "markdownlint", "textlint"]
    assert report["display"] == {"total": 4, "returned": 3, "omitted": 1}


def test_rejects_success_exit_with_findings(tmp_path):
    directory = make_run(tmp_path, 1)
    with pytest.raises(ValueError, match="exit code"):
        record(directory)


@pytest.mark.parametrize("stability", ["captured", "changed"])
def test_context_without_a_stable_finish_cannot_support_success(tmp_path, stability):
    directory = make_run(tmp_path)
    captured = {"stability": stability, "comparison_counts": {"different": 1, "unknown": 0}}
    (directory / "context.json").write_text(json.dumps(captured), encoding="utf-8")
    with pytest.raises(ValueError, match="stable"):
        record(directory)
    report = record(directory, code=2)
    assert report["context"] == captured
    assert "context" in report["artifacts"]
