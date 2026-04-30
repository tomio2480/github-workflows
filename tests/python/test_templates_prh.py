"""templates/prh.yml の構造に対する回帰テスト．

prh は plain-string パターンを substring match するため，`JS` を裸で書くと
`JSON` 等に誤マッチする．JavaScript ルールの `JS` パターンは word-boundary 付き
regex `/\\bJS\\b/` で書く必要がある．

Issue #15 stage 2 で追加した「全角記号前後の半角スペース禁止」ルール
（4 シンボル：中黒・全角スラッシュ・全角コロン・波ダッシュ）の回帰も
ここで検証する．
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


_PRH_PATH = Path(__file__).resolve().parents[2] / "templates" / "prh.yml"

_FULLWIDTH_SYMBOLS = ("・", "／", "：", "〜")


def test_javascript_rule_does_not_use_bare_js_pattern() -> None:
    content = _PRH_PATH.read_text(encoding="utf-8")
    # 末尾コメント `- JS # ...` および YAML quoted form (`- "JS"` / `- 'JS'`) も検出する．
    bare_js_line = re.search(
        r"^\s*-\s*(?:['\"])?JS(?:['\"])?\s*(?:#.*)?\s*$",
        content,
        re.MULTILINE,
    )
    assert bare_js_line is None, (
        "templates/prh.yml に plain-string `JS` パターンが残っている．"
        "prh は substring match のため `JSON` を誤検出する．"
        "`/\\bJS\\b/` 形式の word-boundary 付き regex に置き換えること．"
    )


def test_javascript_rule_uses_word_boundary_regex_for_js() -> None:
    content = _PRH_PATH.read_text(encoding="utf-8")
    assert "/\\bJS\\b/" in content, (
        "templates/prh.yml に `/\\bJS\\b/` パターンが見当たらない．"
        "JS 単独表記のみ JavaScript に正規化するために必要．"
    )


def _load_rules() -> list[dict]:
    with _PRH_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = data.get("rules") or []
    assert isinstance(rules, list), "templates/prh.yml の rules がリスト形式でない"
    return rules


def _find_rule_by_expected(rules: list[dict], expected: str) -> dict | None:
    for rule in rules:
        if isinstance(rule, dict) and rule.get("expected") == expected:
            return rule
    return None


@pytest.mark.parametrize("symbol", _FULLWIDTH_SYMBOLS)
def test_fullwidth_symbol_rule_present(symbol: str) -> None:
    """4 シンボルそれぞれに対応する rule が存在することを確認する．

    Issue #15 で観測された全角記号前後の半角スペース混入を中央 textlint で
    検出可能にする stage 2 の回帰テスト．
    """
    rules = _load_rules()
    rule = _find_rule_by_expected(rules, symbol)
    assert rule is not None, (
        f"templates/prh.yml に expected:{symbol} の rule が見当たらない．"
        "Issue #15 stage 2 で追加した全角記号前後スペース禁止ルールが欠けている．"
    )


@pytest.mark.parametrize("symbol", _FULLWIDTH_SYMBOLS)
def test_fullwidth_symbol_pattern_uses_longest_first_alternation(symbol: str) -> None:
    """各 rule の patterns が `/ X | X|X /` 形式の長い順 alternation 1 本を
    含むことを確認する．

    prh は同一 rule 内の複数 pattern を内部で alternation に合成し /g 適用するため，
    `[/ X/, /X /]` のように pattern を分けても両側スペース（例: `CI ・ cron`）の
    後続スペースが消えずに spec test が落ちる．長い順 alternation `/ X | X|X /` で
    leftmost-longest を機能させ，両側スペースを 1 マッチで `X` に置換する設計．
    """
    rules = _load_rules()
    rule = _find_rule_by_expected(rules, symbol)
    assert rule is not None
    patterns = rule.get("patterns") or []
    expected_regex = f"/ {symbol} | {symbol}|{symbol} /"
    assert expected_regex in patterns, (
        f"templates/prh.yml の expected:{symbol} rule に `{expected_regex}` パターンが無い．"
        "両側スペースを 1 マッチで処理するため長い順 alternation が必要．"
    )


@pytest.mark.parametrize("symbol", _FULLWIDTH_SYMBOLS)
def test_fullwidth_symbol_rule_has_specs(symbol: str) -> None:
    """各 rule に specs が定義され from/to が non-empty であることを確認する．

    prh の specs は YAML 内で from/to を assert する組み込みテスト機構．
    rule の意図を YAML 内に閉じ込めることで仕様の自己文書化と回帰検出を兼ねる．
    """
    rules = _load_rules()
    rule = _find_rule_by_expected(rules, symbol)
    assert rule is not None
    specs = rule.get("specs") or []
    assert specs, f"templates/prh.yml の expected:{symbol} rule に specs が定義されていない．"
    for i, spec in enumerate(specs):
        assert isinstance(spec, dict), f"specs[{i}] が dict ではない: {spec!r}"
        assert spec.get("from"), f"specs[{i}].from が空 (rule expected:{symbol})"
        assert spec.get("to"), f"specs[{i}].to が空 (rule expected:{symbol})"
