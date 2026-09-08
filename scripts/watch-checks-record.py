"""Record native observations; the shell entry points own the waiting policy."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


BUCKETS = ("pass", "fail", "pending", "skipping", "cancel")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_checks(raw):
    data = json.loads(raw)
    if not isinstance(data, list) or any(
        not isinstance(item, dict) or item.get("bucket") not in BUCKETS
        or not isinstance(item.get("name"), str) for item in data
    ):
        raise ValueError("checks must be an array with names and known buckets")
    return data


def query(directory, kind, command):
    prefix = f"{len(list((directory / 'queries').glob('*.json'))) + 1:06d}-{kind}"
    base = directory / "queries" / prefix
    started = timestamp()
    try:
        command = [shutil.which(command[0]) or command[0], *command[1:]]
        result = subprocess.run(command, capture_output=True, check=False)
        code, raw, diagnostic = result.returncode, result.stdout, result.stderr
    except OSError as error:
        code, raw, diagnostic = 1, b"", str(error).encode("utf-8")
    base.with_suffix(".stdout").write_bytes(raw)
    base.with_suffix(".stderr").write_bytes(diagnostic)
    output = raw
    valid = None
    if kind == "checks":
        try:
            checks = parse_checks(raw)
            output = "".join(item["bucket"] + "\n" for item in checks).encode("utf-8")
            valid = True
        except (ValueError, UnicodeError) as error:
            output, valid = b"", False
            diagnostic += f"\ninvalid checks response: {error}\n".encode("utf-8")
    write_json(base.with_suffix(".json"), {
        "kind": kind, "started_at": started, "completed_at": timestamp(),
        "argv": command, "exit_code": code, "valid_checks": valid,
        "stdout": base.with_suffix(".stdout").name,
        "stderr": base.with_suffix(".stderr").name,
    })
    with (directory / "diagnostics.log").open("ab") as log:
        log.write(diagnostic)
    sys.stdout.buffer.write(output)
    sys.stderr.buffer.write(diagnostic)
    return code if valid is not False else 1


def preview(item):
    result = {}
    truncated = False
    for key in ("name", "bucket", "state", "link"):
        value = " ".join(str(item.get(key) or "").split())
        truncated |= len(value) > 160
        result[key] = value[:160] + ("…" if len(value) > 160 else "")
    return dict(result, truncated=truncated)


def finish(args):
    directory = Path(args.run_dir)
    queries = [json.loads(path.read_text(encoding="utf-8"))
               for path in sorted((directory / "queries").glob("*.json"))]
    last_checks = next((query for query in reversed(queries) if query["kind"] == "checks"), None)
    last_head = next((query for query in reversed(queries) if query["kind"] == "head"), None)
    checks = None
    if last_checks and last_checks["valid_checks"]:
        checks = parse_checks((directory / "queries" / last_checks["stdout"]).read_bytes())
        write_json(directory / "checks.json", checks)
    counts = {bucket: sum(item["bucket"] == bucket for item in checks) for bucket in BUCKETS} if checks is not None else None
    observed = (directory / "queries" / last_head["stdout"]).read_text(encoding="utf-8").strip() if last_head else ""
    observed = observed if len(observed) == 40 and all(c in "0123456789abcdefABCDEF" for c in observed) else None
    status = {0: "ok", 1: "error", 2: "partial", 3: "findings"}.get(args.code, "error")
    if args.code == 0 and counts and counts["skipping"] == len(checks):
        status = "not_applicable"
    shown = sorted(checks or [], key=lambda item: BUCKETS.index(item["bucket"]) if item["bucket"] != "pass" else 5)[:args.limit]
    report = {
        "schema_version": 1, "tool": "watch-pr-checks", "status": status,
        "exit_code": args.code, "reason": args.reason, "pr": args.pr,
        "expected_sha": args.expected_sha or None, "observed_sha": observed,
        "run_dir": str(directory.resolve()), "completed_at": timestamp(),
        "coverage": {"scope": "observed_checks", "total": len(checks) if checks is not None else None,
                     "observation_complete": args.code in (0, 3) and checks is not None and observed == args.expected_sha,
                     "expected_checks_complete": None},
        "counts": counts,
        "display": {"returned": len(shown), "omitted": len(checks) - len(shown) if checks is not None else None, "limit": args.limit},
        "checks": [preview(item) for item in shown],
        "artifacts": {key: str((directory / name).resolve()) for key, name in (
            ("full", "full.txt"), ("diagnostics", "diagnostics.log"),
            ("queries", "queries"), ("report", "report.json"), ("summary", "summary.txt"))},
    }
    report["context"] = json.loads((directory / "context.json").read_text(encoding="utf-8"))
    summary = [f"watch-pr-checks: {status} (exit {args.code}; {args.reason})",
               f"PR #{args.pr}: target={args.expected_sha or 'unknown'} observed={observed or 'unknown'}",
               "counts: " + (", ".join(f"{key}={value}" for key, value in counts.items()) if counts else "unknown"),
               "expected checks: unknown (observed checks only)",
               f"display: returned={len(shown)} omitted={report['display']['omitted']}"]
    summary += [f"- {item['bucket']}: {item['name']} {item['link']}" for item in report["checks"]]
    summary += [f"full: {report['artifacts']['full']}", f"report: {report['artifacts']['report']}"]
    (directory / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    write_json(directory / "report.json", report)
    if args.format == "json":
        sys.stdout.buffer.write((directory / "report.json").read_bytes())
    elif args.format == "summary":
        sys.stdout.buffer.write((directory / "summary.txt").read_bytes())
    return args.code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    init = commands.add_parser("init")
    init.add_argument("--output-dir", default="")
    init.add_argument("--timeout", type=int, required=True)
    init.add_argument("--interval", type=int, required=True)
    init.add_argument("--settle", type=int, required=True)
    native = commands.add_parser("query")
    native.add_argument("run_dir")
    native.add_argument("kind", choices=("head", "resolve", "checks"))
    native.add_argument("command", nargs=argparse.REMAINDER)
    final = commands.add_parser("finish")
    final.add_argument("--run-dir", required=True)
    final.add_argument("--code", required=True, type=int)
    final.add_argument("--reason", required=True)
    final.add_argument("--expected-sha", default="")
    final.add_argument("--pr", required=True)
    final.add_argument("--format", choices=("full", "summary", "json"), required=True)
    final.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.operation == "init":
            parent = Path(args.output_dir or tempfile.gettempdir()).resolve()
            parent.mkdir(parents=True, exist_ok=True)
            directory = Path(tempfile.mkdtemp(prefix="watch-pr-checks-", dir=parent))
            (directory / "queries").mkdir()
            for name in ("full.txt", "diagnostics.log"):
                (directory / name).touch()
            write_json(directory / "context.json", {
                "cwd": str(Path.cwd()), "started_at": timestamp(), "gh_repo": os.environ.get("GH_REPO"),
                "timeout_seconds": args.timeout, "interval_seconds": args.interval,
                "settle_seconds": args.settle,
            })
            print(directory.as_posix())
            return 0
        if args.operation == "query":
            return query(Path(args.run_dir), args.kind, args.command)
        return finish(args)
    except (OSError, ValueError) as error:
        print(f"watch-pr-checks record error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
