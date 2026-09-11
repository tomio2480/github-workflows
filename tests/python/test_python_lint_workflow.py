from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(path):
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_python_gate_is_blocking_and_retains_results():
    workflow = load(".github/workflows/python-lint.yml")
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["lint"]
    assert "continue-on-error" not in job
    run = next(s for s in job["steps"] if "run" in s)
    assert "continue-on-error" not in run
    assert "${{" not in run["run"]
    assert '--python "${PYTHON_VERSION}"' in run["run"]
    assert "--locked" in run["run"]
    assert "test -f uv.lock" in run["run"]
    assert run["env"]["VERIFY_SCRIPT"] == "${{ inputs.verify-script }}"
    artifact = job["steps"][-1]
    assert artifact["if"] == "${{ always() }}"
    assert artifact["with"]["path"] == "${{ runner.temp }}/python-lint"
    assert job["steps"][0]["with"]["persist-credentials"] is False


def test_self_caller_and_dependency_updates_cover_python_assets():
    jobs = load(".github/workflows/test-self-lint.yml")["jobs"]
    caller = jobs["python-lint-reusable"]
    assert caller["uses"] == "./.github/workflows/python-lint.yml"
    project = ROOT / caller["with"]["working-directory"]
    assert (
        project / caller["with"]["verify-script"]
    ).resolve() == ROOT / "templates/verify-python.py"
    assert (project / "uv.lock").is_file()
    controls = jobs["python-lint-controls"]["steps"]
    assert any("test_python_quality.py" in s.get("run", "") for s in controls)
    updates = load(".github/dependabot.yml")["updates"]
    assert any(
        u["package-ecosystem"] == "uv"
        and u.get("directory") == "/tests/fixtures/python-quality"
        for u in updates
    )
    assert any(
        u["package-ecosystem"] == "github-actions" and "/" in u.get("directories", [])
        for u in updates
    )
