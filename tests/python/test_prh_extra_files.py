"""templates/.prh-extra.yml と root の .prh-extra.yml の構造テスト（Issue #91）．

どちらも textlint-rule-prh が rulePaths の 1 本として読む辞書のため，
`version: 1` と list 型の `rules` を持つ prh 辞書として parse できることを保証する．
root の辞書は統合テスト fixture の効き目確認に使うため，少なくとも 1 規則を持つ．
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _ROOT / "templates" / ".prh-extra.yml"
_DOGFOOD = _ROOT / ".prh-extra.yml"


def _load(path: Path) -> dict:
    body = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(body, dict), f"{path.name} の root は mapping であること"
    return body


@pytest.mark.parametrize("path", [_TEMPLATE, _DOGFOOD], ids=["template", "dogfood"])
def test_prh_extra_is_a_valid_prh_dictionary(path: Path) -> None:
    body = _load(path)
    assert body.get("version") == 1
    assert isinstance(body.get("rules"), list)


def test_template_prh_extra_has_no_active_rules() -> None:
    """雛形は空辞書として動く（コピー直後の caller に指摘を増やさない）．"""
    assert _load(_TEMPLATE)["rules"] == []


def test_dogfood_prh_extra_has_at_least_one_rule_with_patterns() -> None:
    rules = _load(_DOGFOOD)["rules"]
    assert rules, "root .prh-extra.yml は fixture 検証用に 1 規則以上を持つこと"
    for rule in rules:
        assert "expected" in rule and rule.get("patterns"), rule
