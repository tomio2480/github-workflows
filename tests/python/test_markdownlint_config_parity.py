"""中央テンプレと自己設定の markdownlint 設定がずれていないことを確かめる．

仕様:
    - templates/.markdownlint-cli2.yaml（caller へ配る設定）と root の
      .markdownlint-cli2.yaml（自己テスト用）は，ignores 以外のキーが一致する
    - ignores の差は，root が tests/fixtures/** を外している点だけである
      （自己テストは fixture の違反を検出できることを確かめるため）

背景:
    自己テスト（test-self-lint.yml の integration-action）は caller-first の解決で
    root の設定を使う．templates 側で規則を変えても自己テストには現れない．
    両者の一致をここで検査し，templates の規則（MD060 の無効化など）を守る．
"""

from __future__ import annotations

from pathlib import Path

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_IGNORE = "tests/fixtures/**"


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _configs() -> tuple[dict, dict]:
    root = _load(_REPO_ROOT / ".markdownlint-cli2.yaml")
    templates = _load(_REPO_ROOT / "templates" / ".markdownlint-cli2.yaml")
    return root, templates


def test_root_and_templates_have_the_same_rule_config():
    root, templates = _configs()
    assert root["config"] == templates["config"]


def test_root_and_templates_differ_only_in_ignores():
    root, templates = _configs()
    assert set(root) == set(templates)
    for key in root:
        if key == "ignores":
            continue
        assert root[key] == templates[key], key


def test_root_ignores_drop_only_the_fixture_entry():
    root, templates = _configs()
    assert _FIXTURE_IGNORE in templates["ignores"]
    assert root["ignores"] == [p for p in templates["ignores"] if p != _FIXTURE_IGNORE]
