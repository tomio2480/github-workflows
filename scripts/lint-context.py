#!/usr/bin/env python3
"""Record resolved lint inputs and compare direct caller declarations (docs/local-lint.md)."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import yaml


ACTION = ".github/actions/markdown-lint"
PUBLIC_INPUTS = ("node-version", "markdown-glob", "markdown-ignore")


class WorkflowLoader(yaml.BaseLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        if not isinstance(key_node, yaml.ScalarNode) or key_node.value in result:
            raise ValueError("non-scalar or duplicate workflow key")
        if key_node.value == "<<":
            raise ValueError("workflow merge keys are not interpreted")
        result[key_node.value] = loader.construct_object(value_node, deep=True)
    return result


WorkflowLoader.add_constructor("tag:yaml.org,2002:map", unique_mapping)


def parse_workflow(data):
    # BaseLoader keeps `on` and version strings intact, without YAML 1.1 coercion.
    document = yaml.load(data, Loader=WorkflowLoader)
    if not isinstance(document, dict):
        raise ValueError("workflow must be a mapping")
    return document


def git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], check=False,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_text(root, *args):
    value = git(root, *args)
    return value.decode("utf-8", "replace").strip() if value is not None else None


def normalized_hash(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def fingerprint(path, caller, central):
    path = Path(path).absolute()
    data = path.read_bytes()
    origin, relative = "external", None
    roots = (("caller", caller), ("central", central)) if path.parent == caller else (
        ("central", central), ("caller", caller))
    for label, root in roots:
        try:
            relative = path.relative_to(root).as_posix()
            origin = label
            break
        except ValueError:
            continue
    return {"path": str(path), "origin": origin, "relative": relative,
            "sha256": hashlib.sha256(data).hexdigest(), "normalized_sha256": normalized_hash(data)}


def node_runtime(executable):
    resolved = shutil.which(executable)
    try:
        result = subprocess.run([resolved or executable, "--version"], check=False,
                                capture_output=True, timeout=10)
        value = result.stdout.decode("utf-8", "replace").strip()
        version = value[1:] if result.returncode == 0 and re.fullmatch(r"v\d+\.\d+\.\d+", value) else None
    except (OSError, subprocess.TimeoutExpired):
        version = None
    return {"executable": resolved, "version": version}


def declarations(caller):
    calls, unresolved, errors, files = [], [], [], []
    folder = caller / ".github/workflows"
    for path in sorted(set(folder.glob("*.yml")) | set(folder.glob("*.yaml"))):
        relative = path.relative_to(caller).as_posix()
        files.append(path)
        try:
            document = parse_workflow(path.read_bytes())
            jobs = document.get("jobs")
            if not isinstance(jobs, dict):
                raise ValueError("jobs must be a mapping")
            trigger = document.get("on", {})
            events = list(trigger) if isinstance(trigger, (dict, list)) else [trigger]
            for name, job in jobs.items():
                if not isinstance(job, dict):
                    raise ValueError("job must be a mapping")
                if "uses" in job:
                    unresolved.append({"workflow": relative, "job": name, "reason": "reusable_workflow"})
                steps = job.get("steps", [])
                if not isinstance(steps, list):
                    raise ValueError("steps must be a sequence")
                for index, step in enumerate(steps):
                    if not isinstance(step, dict):
                        raise ValueError("step must be a mapping")
                    uses = step.get("uses", "")
                    if not isinstance(uses, str):
                        raise ValueError("uses must be a scalar")
                    if ACTION not in uses:
                        if "${{" in uses:
                            unresolved.append({"workflow": relative, "job": name, "reason": "uses_expression"})
                        continue
                    inputs = step.get("with", {})
                    if not isinstance(inputs, dict):
                        raise ValueError("with must be a mapping")
                    calls.append({"workflow": relative, "job": name, "step": index + 1,
                                  "uses": uses, "events": events,
                                  "condition": job.get("if") if isinstance(job.get("if"), str) else None,
                                  "step_condition": step.get("if") if isinstance(step.get("if"), str) else None,
                                  "inputs": {key: inputs[key] if isinstance(inputs[key], str) else None
                                             for key in PUBLIC_INPUTS if key in inputs}})
        except (OSError, ValueError, yaml.YAMLError, RecursionError):
            errors.append({"workflow": relative, "reason": "invalid_or_unsupported_yaml"})
    return calls, unresolved, errors, files


def item(field, state, *, expected=None, actual=None, reason=None):
    return {"field": field, "state": state, "expected": expected, "actual": actual, "reason": reason}


def node_comparison(expected, actual):
    if not isinstance(expected, str) or not actual:
        return item("node", "unknown", expected=expected, actual=actual)
    if re.fullmatch(r"\d+", expected):
        state = "same" if expected == actual.split(".")[0] else "different"
        return item("node", state, expected=expected, actual=actual, reason="major_only")
    if re.fullmatch(r"\d+\.\d+\.\d+", expected):
        return item("node", "same" if expected == actual else "different", expected=expected, actual=actual)
    return item("node", "unknown", expected=expected, actual=actual, reason="expression_or_version_range")


def normalized_ignore(value):
    """Read markdown-ignore as the action does: one pattern per line.

    action.yml (summary step) splits on newlines and drops only empty lines.
    count-lint-findings.py then strips each pattern and turns backslashes into slashes.
    It fails on a whitespace-only pattern, so such a value returns None: no local run can match it.
    A YAML block scalar ends with a newline that must not decide the comparison.
    """
    patterns = [line.strip().replace("\\", "/") for line in value.split("\n") if line]
    return "\n".join(patterns) if all(patterns) else None


def declaration_item(field, expected, actual, normalize=lambda value: value):
    if not isinstance(expected, str) or "${{" in expected:
        return item(field, "unknown", expected=expected, actual=actual, reason="declaration_only")
    normalized_expected, normalized_actual = normalize(expected), normalize(actual)
    if normalized_expected is None or normalized_actual is None:
        # Keep the raw values so the record shows the pattern the action rejects.
        return item(field, "different", expected=expected, actual=actual, reason="declaration_only")
    return item(field, "same" if normalized_expected == normalized_actual else "different",
                expected=normalized_expected, actual=normalized_actual, reason="declaration_only")


def compare_call(call, report, central):
    reference = re.fullmatch(r"([^/]+/[^/]+)/" + re.escape(ACTION) + r"@([0-9a-fA-F]{40})", call["uses"])
    pin, metadata = None, None
    if reference and reference[1].lower() == (report["source"]["identity"] or "").lower():
        pin = reference[2].lower()
        data = git(central, "show", f"{pin}:{ACTION}/action.yml")
        if data is None:
            data = git(central, "show", f"{pin}:{ACTION}/action.yaml")
        if data is not None:
            try:
                metadata = parse_workflow(data)
            except (ValueError, yaml.YAMLError, RecursionError):
                pass
    comparisons = [item("central_ref", "unknown" if pin is None or not report["source"]["head"] else
                        "same" if pin == report["source"]["head"] else "different",
                        expected=pin, actual=report["source"]["head"])]
    defaults = metadata.get("inputs", {}) if isinstance(metadata, dict) else {}
    effective = {}
    for key in PUBLIC_INPUTS:
        declaration = defaults.get(key, {}) if isinstance(defaults, dict) else {}
        default = declaration.get("default") if isinstance(declaration, dict) else None
        effective[key] = call["inputs"].get(key, default)
    if metadata is None:
        comparisons.append(item("node", "unknown", reason="pinned_definition_unavailable"))
    else:
        comparisons.append(node_comparison(effective["node-version"], report["runtime"]["node"]["version"]))
    # The glob reaches the linters verbatim as one argument, so only the ignore list has line semantics.
    comparisons.append(declaration_item("markdown-glob", effective["markdown-glob"], report["selection"]["glob"]))
    comparisons.append(declaration_item("markdown-ignore", effective["markdown-ignore"],
                                        "\n".join(report["selection"]["ignore"]), normalized_ignore))
    for role, file in report["files"].items():
        if role.startswith("workflow:") or role.startswith("runtime:"):
            continue
        expected = None
        if metadata is None:
            state = "unknown"
        elif file["origin"] == "caller":
            state = "caller_override"
        elif file["origin"] == "central":
            data = git(central, "show", f"{pin}:{file['relative']}")
            expected = normalized_hash(data) if data is not None else None
            state = "unknown" if expected is None else (
                "same" if expected == file["normalized_sha256"] else "different")
        else:
            state = "unknown"
        comparisons.append(item("file:" + role, state, expected=expected, actual=file["normalized_sha256"]))
    call["comparisons"] = comparisons


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(4):
        try:
            temporary.replace(path)
            return
        except PermissionError as error:
            if getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 3:
                raise
            time.sleep(0.1 * (attempt + 1))


def capture(args):
    caller, central = args.root.resolve(), args.central.resolve()
    origin = git_text(central, "remote", "get-url", "origin") or ""
    identity = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", origin, re.IGNORECASE)
    dirty = git(central, "status", "--porcelain=v1", "--untracked-files=normal")
    calls, unresolved, errors, workflows = declarations(caller)
    files = dict(args.file or [])
    files.update({"workflow:" + path.relative_to(caller).as_posix(): str(path) for path in workflows})
    for name in ("package.json", "package-lock.json"):
        files["dependency:" + name] = str(central / ACTION / name)
    report = {
        "schema_version": 1, "captured_at": datetime.now(timezone.utc).isoformat(),
        "stability": "captured", "root": str(caller),
        "source": {"root": str(central), "head": git_text(central, "rev-parse", "HEAD"),
                   "identity": identity[1] if identity else None,
                   "dirty": bool(dirty) if dirty is not None else None},
        "runtime": {"node": node_runtime(args.node),
                    "python": {"executable": sys.executable, "version": sys.version.split()[0]},
                    "pyyaml": yaml.__version__},
        "selection": {"glob": args.glob, "ignore": args.ignore or []},
        "files": {role: fingerprint(path, caller, central) for role, path in files.items() if path},
        "calls": calls, "unresolved_calls": unresolved, "workflow_errors": errors,
    }
    for call in calls:
        compare_call(call, report, central)
    counts = Counter(row["state"] for call in calls for row in call["comparisons"])
    counts["unknown"] += len(unresolved) + len(errors) + (1 if not calls else 0)
    report["comparison_counts"] = {state: counts[state] for state in ("same", "different", "unknown", "caller_override")}
    save(args.output, report)


def finish(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    changed = []
    for role, file in report["files"].items():
        try:
            current = hashlib.sha256(Path(file["path"]).read_bytes()).hexdigest()
        except OSError:
            current = None
        if current != file["sha256"]:
            changed.append(role)
    report["changed_files"] = changed
    report["stability"] = "changed" if changed else "stable"
    save(path, report)
    return 2 if changed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("capture")
    start.add_argument("--output", type=Path, required=True)
    start.add_argument("--root", type=Path, required=True)
    start.add_argument("--central", type=Path, required=True)
    start.add_argument("--node", default="node")
    start.add_argument("--glob", default="**/*.md")
    start.add_argument("--ignore", action="append")
    start.add_argument("--file", nargs=2, action="append", metavar=("ROLE", "PATH"))
    end = commands.add_parser("finish")
    end.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "capture":
            capture(args)
            return 0
        return finish(args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"lint-context: cannot record context: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
