"""Local lint context records facts without evaluating workflow expressions."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/lint-context.py"
ACTION = ".github/actions/markdown-lint"


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def workspace(tmp_path):
    central = tmp_path / "central 日本語"
    caller = tmp_path / "caller space '$"
    for root in (central, caller):
        root.mkdir()
        git(root, "init", "-q")
        git(root, "config", "user.name", "fixture")
        git(root, "config", "user.email", "fixture@example.invalid")
        git(root, "config", "core.autocrlf", "false")
    git(central, "remote", "add", "origin", "https://github.com/example/central.git")
    action = central / ACTION
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        'inputs:\n  node-version:\n    default: "20"\n'
        '  markdown-glob:\n    default: "**/*.md"\n'
        '  markdown-ignore:\n    default: ""\nruns:\n  using: composite\n  steps: []\n',
        encoding="utf-8",
    )
    for name in ("package.json", "package-lock.json"):
        (action / name).write_text("{}\n", encoding="utf-8")
    (central / "templates").mkdir()
    (central / "templates/prh.yml").write_text("rules: []\n", encoding="utf-8")
    git(central, "add", ".")
    git(central, "commit", "-qm", "baseline")
    pin = git(central, "rev-parse", "HEAD")
    (caller / ".github/workflows").mkdir(parents=True)
    return central, caller, pin, tmp_path / "record space 日本語.json"


def workflow(caller, pin, *, extra="", uses=None, filename="lint.yml"):
    uses = uses or f"example/central/{ACTION}@{pin}"
    path = caller / ".github/workflows" / filename
    path.write_text(
        "on:\n  pull_request:\n    paths: ['**/*.md']\njobs:\n  lint:\n"
        "    if: github.event_name == 'pull_request'\n    runs-on: ubuntu-latest\n"
        f"    steps:\n      - uses: '{uses}'\n{extra}", encoding="utf-8",
    )
    return path


def capture(workspace, *extra):
    central, caller, _, output = workspace
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "capture", "--output", str(output),
         "--root", str(caller), "--central", str(central),
         "--node", sys.executable, "--glob", "**/*.md",
         "--file", "prh", str(central / "templates/prh.yml"), *extra],
        capture_output=True, env={**os.environ, "PYTHONUTF8": "1"}, check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout == b""
    return json.loads(output.read_text(encoding="utf-8"))


def comparison(report, field, call=0):
    return next(row for row in report["calls"][call]["comparisons"] if row["field"] == field)


def test_pin_defaults_and_hashes_are_read_from_the_pinned_object(workspace):
    central, caller, pin, _ = workspace
    workflow(caller, pin)
    report = capture(workspace)
    assert comparison(report, "central_ref")["state"] == "same"
    assert comparison(report, "node")["expected"] == "20"
    assert comparison(report, "node")["state"] == "unknown"
    assert comparison(report, "file:prh")["state"] == "same"
    assert report["calls"][0]["condition"] == "github.event_name == 'pull_request'"
    assert report["calls"][0]["events"] == ["pull_request"]
    assert report["files"]["prh"]["sha256"] == hashlib.sha256((central / "templates/prh.yml").read_bytes()).hexdigest()
    assert report["files"]["prh"]["normalized_sha256"] == hashlib.sha256(b"rules: []\n").hexdigest()
    assert report["runtime"]["python"]["executable"] == sys.executable
    assert report["runtime"]["pyyaml"]


def test_old_pin_and_same_head_uncommitted_config_are_distinguished(workspace):
    central, caller, pin, _ = workspace
    workflow(caller, pin)
    (central / "templates/prh.yml").write_text("rules: [{expected: word}]\n", encoding="utf-8")
    report = capture(workspace)
    assert report["source"]["dirty"] is True
    assert comparison(report, "central_ref")["state"] == "same"
    assert comparison(report, "file:prh")["state"] == "different"
    git(central, "add", ".")
    git(central, "commit", "-qm", "changed config")
    report = capture(workspace)
    assert comparison(report, "central_ref")["state"] == "different"
    assert report["source"]["dirty"] is False


def test_caller_override_is_recorded_without_dumping_token_inputs(workspace):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra='        with:\n          node-version: "22"\n'
             '          github-token: literal-secret-fixture\n')
    override = caller / "prh.yml"
    override.write_text("rules: []\n", encoding="utf-8")
    report = capture(workspace, "--file", "prh", str(override))
    assert comparison(report, "node")["expected"] == "22"
    assert comparison(report, "file:prh")["state"] == "caller_override"
    assert "literal-secret-fixture" not in json.dumps(report)


@pytest.mark.parametrize("ref", ["a" * 40, "main", "${{ inputs.ref }}"])
def test_unknown_ref_never_falls_back_to_local_head(workspace, ref):
    _, caller, _, _ = workspace
    workflow(caller, ref)
    report = capture(workspace)
    assert comparison(report, "node")["state"] == "unknown"
    assert comparison(report, "file:prh")["state"] == "unknown"


def test_expression_and_range_are_unknown_and_each_call_is_preserved(workspace):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra='        with:\n          node-version: "${{ matrix.node }}"\n')
    workflow(caller, pin, extra='        with:\n          node-version: ">=20"\n', filename="other.yaml")
    report = capture(workspace)
    assert len(report["calls"]) == 2
    assert all(comparison(report, "node", i)["state"] == "unknown" for i in range(2))


@pytest.mark.parametrize("body", ["jobs: [", "jobs: {}\njobs: {}\n", "---\njobs: {}\n---\njobs: {}\n"])
def test_invalid_or_ambiguous_yaml_is_not_an_empty_success(workspace, body):
    _, caller, _, _ = workspace
    (caller / ".github/workflows/bad.yml").write_text(body, encoding="utf-8")
    report = capture(workspace)
    assert report["workflow_errors"]
    assert report["comparison_counts"]["unknown"] > 0


def test_run_text_is_not_a_uses_key_and_reusable_call_is_unknown(workspace):
    _, caller, pin, _ = workspace
    (caller / ".github/workflows/fixture.yml").write_text(
        "on: push\njobs:\n  script:\n    runs-on: ubuntu-latest\n    steps:\n"
        f"      - run: |\n          uses: example/central/{ACTION}@{pin}\n"
        f"  wrapper:\n    uses: example/central/.github/workflows/wrapped.yml@{pin}\n",
        encoding="utf-8",
    )
    report = capture(workspace)
    assert not report["calls"]
    assert report["unresolved_calls"][0]["reason"] == "reusable_workflow"


def test_finish_detects_a_config_change_and_keeps_original_hash(workspace):
    central, caller, pin, output = workspace
    workflow(caller, pin)
    before = capture(workspace)
    (central / "templates/prh.yml").write_text("rules: [changed]\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "finish", str(output)], capture_output=True)
    assert result.returncode == 2
    after = json.loads(output.read_text(encoding="utf-8"))
    assert after["stability"] == "changed"
    assert "prh" in after["changed_files"]
    assert after["files"]["prh"]["sha256"] == before["files"]["prh"]["sha256"]


def test_finish_accepts_unchanged_inputs(workspace):
    _, caller, pin, output = workspace
    workflow(caller, pin)
    capture(workspace)
    result = subprocess.run([sys.executable, str(SCRIPT), "finish", str(output)], capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["stability"] == "stable"


@pytest.mark.parametrize("expected,actual,state", [
    ("20", "20.11.1", "same"), ("22", "20.11.1", "different"),
    ("20.11.1", "20.11.1", "same"), ("20.11.0", "20.11.1", "different"),
    (">=20", "22.0.0", "unknown"), ("${{ matrix.node }}", "20.11.1", "unknown"),
    ("20", None, "unknown"), (None, "20.11.1", "unknown"),
])
def test_node_comparison_limits_its_claim_to_major_or_exact_version(expected, actual, state):
    module = importlib.import_module("lint-context")
    assert module.node_comparison(expected, actual)["state"] == state


def declared_ignore(value):
    """Return a caller step whose markdown-ignore input is the given YAML text."""
    return f"        with:\n          markdown-ignore: {value}\n"


def literal_block(*lines):
    """Return a literal block scalar with each line placed at the block indentation."""
    return "|\n" + "\n".join(f"            {line}" for line in lines)


def local_ignores(*patterns):
    return [argument for pattern in patterns for argument in ("--ignore", pattern)]


# The action splits markdown-ignore on newlines and drops only empty lines (action.yml, summary step).
# count-lint-findings.py then strips each pattern, turns backslashes into slashes,
# and fails on a whitespace-only pattern, so such a declaration can never match a local run.
# The caller's YAML style must not decide whether the same patterns count as different.
@pytest.mark.parametrize("declared,local,state", [
    ('"tests/fixtures/**"', ["tests/fixtures/**"], "same"),
    (literal_block("tests/fixtures/**"), ["tests/fixtures/**"], "same"),
    (literal_block("a/**", "b/**"), ["a/**", "b/**"], "same"),
    (literal_block("a/**", "", "  b/** ", "c\\d/**  "), ["a/**", "b/**", "c/d/**"], "same"),
    ('""', [], "same"),
    (literal_block("tests/fixtures/**"), ["docs/**"], "different"),
    (literal_block("a/**", "b/**"), ["a/**"], "different"),
    (literal_block("a/**"), ["a/**", "b/**"], "different"),
    (literal_block("a/**", "  ", "b/**"), ["a/**", "b/**"], "different"),
    ('"   "', [], "different"),
    ('"${{ vars.IGNORE }}"', ["a/**"], "unknown"),
], ids=["flow-scalar", "block-single", "block-multiple", "block-blank-indented-and-padded",
        "empty-declaration", "block-different-pattern", "block-missing-local-pattern",
        "block-extra-local-pattern", "block-whitespace-only-line", "whitespace-only-declaration",
        "expression"])
def test_ignore_declaration_is_compared_as_the_action_reads_it(workspace, declared, local, state):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra=declared_ignore(declared))
    row = comparison(capture(workspace, *local_ignores(*local)), "markdown-ignore")
    assert row["state"] == state
    assert row["reason"] == "declaration_only"


def test_ignore_records_the_patterns_both_sides_were_compared_by(workspace):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra=declared_ignore(literal_block("a/**", "", "  b/** ")))
    row = comparison(capture(workspace, *local_ignores("a/**", "b/**")), "markdown-ignore")
    assert row["expected"] == row["actual"] == "a/**\nb/**"


def test_ignore_keeps_the_raw_declaration_when_the_action_would_reject_it(workspace):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra=declared_ignore('"   "'))
    row = comparison(capture(workspace), "markdown-ignore")
    assert (row["state"], row["expected"], row["actual"]) == ("different", "   ", "")


def test_ignore_keeps_the_raw_expression_when_the_value_is_not_comparable(workspace):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra=declared_ignore('"${{ vars.IGNORE }}\\\\x "'))
    row = comparison(capture(workspace, *local_ignores("a/**")), "markdown-ignore")
    assert (row["state"], row["expected"], row["actual"]) == ("unknown", "${{ vars.IGNORE }}\\x ", "a/**")


def test_ignore_default_without_a_declaration_matches_no_local_ignore(workspace):
    _, caller, pin, _ = workspace
    workflow(caller, pin)
    row = comparison(capture(workspace), "markdown-ignore")
    assert (row["state"], row["expected"], row["actual"]) == ("same", "", "")


# markdown-glob is passed to the linters verbatim as one argument (action.yml, markdownlint step),
# so unlike markdown-ignore it has no line semantics and stays a raw string comparison.
@pytest.mark.parametrize("declared,state", [
    ('"**/*.md"', "same"), (literal_block("**/*.md"), "different"), ('"docs/**/*.md"', "different"),
], ids=["flow-scalar", "block-scalar-keeps-its-newline", "different-pattern"])
def test_glob_declaration_stays_a_raw_string_comparison(workspace, declared, state):
    _, caller, pin, _ = workspace
    workflow(caller, pin, extra=f"        with:\n          markdown-glob: {declared}\n")
    assert comparison(capture(workspace), "markdown-glob")["state"] == state


def test_line_endings_do_not_hide_a_config_value_change(workspace):
    central, caller, pin, _ = workspace
    workflow(caller, pin)
    config = central / "templates/prh.yml"
    config.write_bytes(b"rules: []\n")
    assert comparison(capture(workspace), "file:prh")["state"] == "same"
    config.write_bytes(b"rules: [changed]\r\n")
    assert comparison(capture(workspace), "file:prh")["state"] == "different"


def test_central_as_caller_keeps_its_root_override_separate_from_templates(workspace):
    central, _, pin, _ = workspace
    (central / ".github/workflows").mkdir(parents=True)
    workflow(central, pin)
    override = central / "prh.yml"
    override.write_text("rules: [caller-only]\n", encoding="utf-8")
    report = capture(workspace, "--root", str(central), "--file", "prh", str(override))
    assert comparison(report, "file:prh")["state"] == "caller_override"
    assert comparison(report, "file:dependency:package.json")["state"] == "same"


def test_finish_follows_the_original_config_path_after_symlink_retarget(workspace):
    central, caller, pin, output = workspace
    workflow(caller, pin)
    link = caller / "prh.yml"
    alternative = caller / "other.yml"
    alternative.write_text("rules: [changed]\n", encoding="utf-8")
    try:
        link.symlink_to(central / "templates/prh.yml")
    except OSError:
        pytest.skip("symlink creation is unavailable")
    capture(workspace, "--file", "prh", str(link))
    link.unlink()
    link.symlink_to(alternative)
    result = subprocess.run([sys.executable, str(SCRIPT), "finish", str(output)], capture_output=True)
    assert result.returncode == 2
    assert "prh" in json.loads(output.read_text(encoding="utf-8"))["changed_files"]
