"""Exercise both public shells with real native processes and saved observations."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SHA = "1" * 40
MOVED = "2" * 40
ENGINES = ["bash", "pwsh"] + (["powershell"] if os.name == "nt" else [])
STUB = r'''
import json, os, sys
from pathlib import Path
root = Path(os.environ["WATCH_STUB"])
args = sys.argv[1:]
with (root / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
mode = os.environ.get("WATCH_CASE", "many")
count_file = root / ("checks" if args[:2] == ["pr", "checks"] else "head")
count = int(count_file.read_text()) + 1 if count_file.exists() else 1
count_file.write_text(str(count))
if args[:2] == ["pr", "view"]:
    if mode == "resolve_error":
        print("cannot resolve PR", file=sys.stderr)
        sys.exit(7)
    if mode == "head_error" and count > 1:
        print("head unavailable", file=sys.stderr)
        sys.exit(7)
    if "headRefName" in args[args.index("--json") + 1]:
        print("feature/example\tfalse\ttomio2480\tgithub-workflows")
    else:
        print("2" * 40 if mode == "head_lag" or mode == "moved" and count > 1 else "1" * 40)
    sys.exit(0)
assert args[:2] == ["pr", "checks"], args
if mode == "error":
    print("認証エラー " + "details " * 1000, file=sys.stderr)
    sys.exit(7)
if mode == "invalid":
    print("not json")
    sys.exit(0)
buckets = {
    "many": ["pass"] * 40,
    "fail": ["pass", "fail", "cancel"],
    "skip": ["skipping", "skipping"],
    "pending": ["pending"] if count == 1 else ["pass"],
    "moved": ["pass"],
    "unknown": ["unexpected"],
    "empty": [],
    "head_error": ["pass"],
}[mode]
records = [{"name": "検査 'quoted' " + "長い名前" * 100 + str(i),
            "state": "COMPLETED", "bucket": value,
            "link": "https://example.test/check/" + str(i)}
           for i, value in enumerate(buckets)]
if "--jq" in args:
    print("\n".join(buckets))
else:
    print(json.dumps(records, ensure_ascii=False))
if mode == "many":
    print("native warning 日本語", file=sys.stderr)
sys.exit(8 if "pending" in buckets else 1 if "fail" in buckets else 0)
'''


@pytest.fixture(params=ENGINES)
def cli(request, tmp_path):
    engine = request.param
    executable = shutil.which(engine)
    if not executable:
        pytest.skip(f"{engine} is not installed")
    stub = tmp_path / "native"
    stub.mkdir()
    (stub / "gh.py").write_text(STUB, encoding="utf-8")
    if os.name == "nt":
        (stub / "gh.cmd").write_bytes(
            f'@echo off\r\n"{sys.executable}" -X utf8 "%~dp0gh.py" %*\r\n'.encode()
        )
    (stub / "gh").write_text(
        '#!/usr/bin/env bash\nexec "' + sys.executable.replace("\\", "/")
        + '" -X utf8 "' + str(stub / "gh.py").replace("\\", "/") + '" "$@"\n',
        encoding="utf-8",
    )
    (stub / "gh").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
    env.update(PATH=str(stub) + os.pathsep + os.environ.get("PATH", ""),
               WATCH_STUB=str(tmp_path), PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               TMP=str(tmp_path), TEMP=str(tmp_path))
    output = tmp_path / "記録 with spaces 'quote' $value"

    def run(mode="many", format="json", limit=2, timeout=30, record=True, destination=None, expect=True, no_python=False):
        env["WATCH_CASE"] = mode
        for name in ("head", "checks", "calls.jsonl"):
            (tmp_path / name).unlink(missing_ok=True)
        if engine == "bash":
            args = [executable, str(ROOT / "bin/watch-pr-checks.sh"), "165",
                    "--timeout", str(timeout), "--interval", "0", "--settle", "0"]
            if expect:
                args += ["--expect-sha", SHA]
            if record:
                args += ["--format", format, "--limit", str(limit)]
                if destination is not False:
                    args += ["--output-dir", str(destination or output)]
        else:
            args = [executable, "-NoProfile", "-File", str(ROOT / "bin/watch-pr-checks.ps1"),
                    "-Pr", "165", "-TimeoutSeconds", str(timeout),
                    "-IntervalSeconds", "0", "-SettleSeconds", "0"]
            if expect:
                args += ["-ExpectSha", SHA]
            if record:
                args += ["-Format", format, "-Limit", str(limit)]
                if destination is not False:
                    args += ["-OutputDir", str(destination or output)]
        child_env = env.copy()
        if no_python:
            child_env["PATH"] = os.pathsep.join([str(stub), str(Path(shutil.which("bash")).parent)])
        result = subprocess.run(args, cwd=ROOT, env=child_env, capture_output=True, timeout=45)
        return result

    return run, output, tmp_path


def report(result):
    assert result.stdout, result.stderr.decode("utf-8", errors="replace")
    return json.loads(result.stdout)


def test_saves_all_observations_and_bounds_only_display(cli):
    run, _, tmp = cli
    result = run()
    data = report(result)
    assert result.returncode == 0, result.stderr
    assert data["schema_version"] == 1 and data["tool"] == "watch-pr-checks"
    assert data["status"] == "ok" and data["exit_code"] == 0
    assert data["expected_sha"] == data["observed_sha"] == SHA
    assert data["coverage"] == {"scope": "observed_checks", "total": 40,
                                "observation_complete": True, "expected_checks_complete": None}
    assert data["display"] == {"returned": 2, "omitted": 38, "limit": 2}
    assert len(data["checks"][0]["name"]) <= 161 and data["checks"][0]["truncated"]
    directory = Path(data["run_dir"])
    assert len(json.loads((directory / "checks.json").read_text(encoding="utf-8"))) == 40
    assert "native warning 日本語" in (directory / "diagnostics.log").read_text(encoding="utf-8")
    queries = list((directory / "queries").glob("*.json"))
    calls = [json.loads(line) for line in (tmp / "calls.jsonl").read_text().splitlines()]
    assert len(queries) == len(calls) == 4
    assert (directory / "full.txt").read_text(encoding="utf-8").count("checks passed") == 1
    assert json.loads((directory / "report.json").read_text(encoding="utf-8")) == data
    assert Path(report(run())["run_dir"]) != directory


@pytest.mark.parametrize("mode,code,status,reason,total", [
    ("fail", 3, "findings", "checks_failed", 3),
    ("skip", 0, "not_applicable", "settled", 2),
    ("pending", 0, "ok", "settled", 1),
    ("moved", 2, "partial", "head_changed", 1),
    ("error", 2, "partial", "timeout", None),
    ("invalid", 2, "partial", "timeout", None),
    ("unknown", 2, "partial", "timeout", None),
    ("empty", 2, "partial", "timeout", 0),
    ("head_error", 2, "partial", "head_unavailable", 1),
    ("head_lag", 2, "partial", "timeout", None),
])
def test_outcomes_are_not_turned_into_success(cli, mode, code, status, reason, total):
    run, _, _ = cli
    result = run(mode=mode, timeout=0 if mode in ("error", "invalid", "unknown", "empty", "head_lag") else 30)
    data = report(result)
    assert result.returncode == data["exit_code"] == code
    assert data["status"] == status and data["reason"] == reason
    assert data["coverage"]["total"] == total
    assert data["coverage"]["observation_complete"] == (code in (0, 3))
    if mode == "skip":
        assert data["counts"]["pass"] == 0 and data["counts"]["skipping"] == 2
    if mode == "error":
        assert "認証エラー" not in result.stdout.decode("utf-8")
        assert "認証エラー" in Path(data["artifacts"]["diagnostics"]).read_text(encoding="utf-8")


def test_summary_full_legacy_and_bad_destination(cli):
    run, output, tmp = cli
    legacy = run(record=False)
    assert legacy.returncode == 0 and b"all 40 checks passed" in legacy.stdout
    assert not output.exists()
    full = run(format="full")
    assert full.returncode == 0 and full.stdout == legacy.stdout
    summary = run(format="summary", limit=0)
    assert summary.returncode == 0 and len(summary.stdout) < 2500
    assert b"omitted=40" in summary.stdout and b"report.json" in summary.stdout
    invalid = tmp / "file"
    invalid.write_text("keep", encoding="utf-8")
    result = run(destination=invalid)
    assert result.returncode == 1 and invalid.read_text() == "keep"
    assert not (tmp / "calls.jsonl").exists()


def test_context_and_early_resolution_failure(cli):
    run, _, tmp = cli
    data = report(run(destination=False))
    assert Path(data["run_dir"]).parent == tmp
    assert data["context"]["timeout_seconds"] == 30
    assert data["context"]["interval_seconds"] == data["context"]["settle_seconds"] == 0
    result = run(mode="resolve_error", expect=False)
    data = report(result)
    assert result.returncode == data["exit_code"] == 1
    assert data["status"] == "error" and data["expected_sha"] is None
    assert data["coverage"]["total"] is None
    assert "cannot resolve PR" in Path(data["artifacts"]["diagnostics"]).read_text(encoding="utf-8")
    legacy = run(mode="resolve_error", expect=False, record=False)
    assert legacy.returncode == 1 and b"cannot resolve PR" in legacy.stderr


@pytest.mark.skipif(os.name != "nt", reason="isolated Windows PATH fixture")
def test_python_is_required_only_for_records(cli):
    run, _, tmp = cli
    result = run(no_python=True)
    assert result.returncode == 1 and b"Python" in result.stderr
    assert not (tmp / "calls.jsonl").exists()
    assert run(no_python=True, record=False).returncode == 0
