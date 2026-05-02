"""templates/prh.yml の構造に対する回帰テスト．

prh は plain-string パターンを substring match するため，`JS` を裸で書くと
`JSON` 等に誤マッチする．JavaScript ルールの `JS` パターンは word-boundary 付き
regex `/\\bJS\\b/` で書く必要がある．

Issue #15 stage 2 で追加した「全角記号前後の半角スペース禁止」ルール
（4 シンボル：中黒・全角スラッシュ・全角コロン・波ダッシュ）の回帰も
ここで検証する．

Issue #33 で追加した「`ユーザ` rule の否定先読み」 の回帰も検証する．
plain string `ユーザ` のままだと `ユーザー` 内の `ユーザ` 部分にも substring
match して誤検出する．`/ユーザ(?!ー)/` 形式の正規表現に置き換える必要がある．
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


def _load_prh_rules() -> list[dict]:
    """templates/prh.yml をロードして rules リストを返す．

    fail-fast 設計：YAML が空・rules キー欠落・rules が list でない いずれの
    異常でも明示的な例外を送出する．silent fallback で「rules が空のリスト」
    として扱うと回帰テストが偽 green になるため避ける．
    """
    with _PRH_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"{_PRH_PATH} が空または無効な YAML です")
    if not isinstance(data, dict):
        raise TypeError(
            f"{_PRH_PATH} の root が dict でなく {type(data).__name__} です"
        )
    rules = data.get("rules")
    if rules is None:
        raise ValueError(f"{_PRH_PATH} に rules キーがありません")
    if not isinstance(rules, list):
        raise TypeError(
            f"{_PRH_PATH} の rules がリストでなく {type(rules).__name__} です"
        )
    return rules


@pytest.fixture(scope="module")
def prh_rules() -> list[dict]:
    """parametrize 用の fixture．

    scope=module で複数のパラメタライズドテストにわたり 1 度だけロードする．
    fail-fast 例外を上げるロード処理は `_load_prh_rules()` に統一している．
    """
    return _load_prh_rules()


def _find_rule_by_expected(rules: list[dict], expected: str) -> dict | None:
    for rule in rules:
        if isinstance(rule, dict) and rule.get("expected") == expected:
            return rule
    return None


@pytest.mark.parametrize("symbol", _FULLWIDTH_SYMBOLS)
def test_fullwidth_symbol_rule_present(symbol: str, prh_rules: list[dict]) -> None:
    """4 シンボルそれぞれに対応する rule が存在することを確認する．

    Issue #15 で観測された全角記号前後の半角スペース混入を中央 textlint で
    検出可能にする stage 2 の回帰テスト．
    """
    rule = _find_rule_by_expected(prh_rules, symbol)
    assert rule is not None, (
        f"templates/prh.yml に expected:{symbol} の rule が見当たらない．"
        "Issue #15 stage 2 で追加した全角記号前後スペース禁止ルールが欠けている．"
    )


@pytest.mark.parametrize("symbol", _FULLWIDTH_SYMBOLS)
def test_fullwidth_symbol_pattern_uses_longest_first_alternation(
    symbol: str, prh_rules: list[dict]
) -> None:
    """各 rule の patterns が `/ +X +| +X|X +/` 形式の長い順 alternation 1 本を
    含むことを確認する．

    prh は同一 rule 内の複数 pattern を内部で alternation に合成し /g 適用するため，
    `[/ X/, /X /]` のように pattern を分けても両側スペース（例: `CI ・ cron`）の
    後続スペースが消えずに spec test が落ちる．長い順 alternation `/ +X +| +X|X +/` で
    leftmost-longest を機能させ，両側スペースを 1 マッチで `X` に置換する設計．
    量指定子 `+` でシングルスペース・ダブルスペース等を一括して扱う．
    """
    rule = _find_rule_by_expected(prh_rules, symbol)
    assert rule is not None
    patterns = rule.get("patterns")
    expected_regex = f"/ +{symbol} +| +{symbol}|{symbol} +/"
    assert patterns == [expected_regex], (
        f"templates/prh.yml の expected:{symbol} rule の patterns は "
        f"`[{expected_regex!r}]` の 1 本のみであるべきだが {patterns!r} が見つかった．"
        "補助 pattern の混在は longest-first 設計を壊すため禁止．"
    )


@pytest.mark.parametrize("symbol", _FULLWIDTH_SYMBOLS)
def test_fullwidth_symbol_rule_has_specs(
    symbol: str, prh_rules: list[dict]
) -> None:
    """各 rule に specs が定義され from/to が non-empty であることを確認する．

    prh の specs は YAML 内で from/to を assert する組み込みテスト機構．
    rule の意図を YAML 内に閉じ込めることで仕様の自己文書化と回帰検出を兼ねる．
    """
    rule = _find_rule_by_expected(prh_rules, symbol)
    assert rule is not None
    specs = rule.get("specs") or []
    assert specs, f"templates/prh.yml の expected:{symbol} rule に specs が定義されていない．"
    for i, spec in enumerate(specs):
        assert isinstance(spec, dict), f"specs[{i}] が dict ではない: {spec!r}"
        assert spec.get("from"), f"specs[{i}].from が空 (rule expected:{symbol})"
        assert spec.get("to"), f"specs[{i}].to が空 (rule expected:{symbol})"


def test_user_rule_does_not_use_bare_user_pattern(prh_rules: list[dict]) -> None:
    """expected:ユーザー rule の patterns が裸の `ユーザ` を含まないこと．

    prh は plain-string パターンを substring match するため `ユーザ` を裸で
    書くと `ユーザー` 内の `ユーザ` 部分にもマッチして誤検出する．
    Issue #33（`tomio2480/settings` PR #37 で 8 件の誤検出を観測）の再発防止．
    """
    rule = _find_rule_by_expected(prh_rules, "ユーザー")
    assert rule is not None, "templates/prh.yml に expected:ユーザー rule が見当たらない"
    patterns = rule.get("patterns") or []
    assert "ユーザ" not in patterns, (
        "templates/prh.yml の expected:ユーザー rule に裸の `ユーザ` plain-string "
        "pattern が残っている．prh は substring match のため正しい表記の "
        "`ユーザー` 内の `ユーザ` にも誤マッチする．"
        "`/ユーザ(?!ー)/` 形式の否定先読み regex に置き換えること．"
    )


def test_user_rule_uses_negative_lookahead_regex(prh_rules: list[dict]) -> None:
    """expected:ユーザー rule の patterns に否定先読み regex が含まれること．

    `/ユーザ(?!ー)/` を含むことで「ユーザ」 単独はヒットさせ「ユーザー」 は
    除外する設計とする．Issue #33 で合意した修正方針．
    """
    rule = _find_rule_by_expected(prh_rules, "ユーザー")
    assert rule is not None
    patterns = rule.get("patterns") or []
    assert "/ユーザ(?!ー)/" in patterns, (
        "templates/prh.yml の expected:ユーザー rule に `/ユーザ(?!ー)/` パターンが見当たらない．"
        "「ユーザー」 を誤検出から除外するために必要．"
    )


def test_user_rule_specs_cover_negative_lookahead(prh_rules: list[dict]) -> None:
    """expected:ユーザー rule の specs に正例と境界例の双方が含まれること．

    - 正例：`ユーザ` 単独 → `ユーザー` に変換される
    - 境界例：`ユーザー` → `ユーザー`（変換されない＝誤検出されない）

    境界例は否定先読み `(?!ー)` が機能することを YAML 内で自己テストする目的．
    prh は from === to の spec を「変換されないことの assert」 として扱う．
    """
    rule = _find_rule_by_expected(prh_rules, "ユーザー")
    assert rule is not None
    specs = rule.get("specs") or []
    assert specs, "templates/prh.yml の expected:ユーザー rule に specs が定義されていない"

    pairs = [(s.get("from"), s.get("to")) for s in specs if isinstance(s, dict)]
    assert any(
        f and t and "ユーザ" in f and "ユーザー" in t and "ユーザー" not in f
        for f, t in pairs
    ), (
        f"expected:ユーザー rule の specs に「`ユーザ` 単独 → `ユーザー`」 の正例が欠けている．"
        f"specs={pairs!r}"
    )
    assert any(
        f == t and f and "ユーザー" in f for f, t in pairs
    ), (
        f"expected:ユーザー rule の specs に「`ユーザー` → `ユーザー`」 の境界例が欠けている．"
        f"否定先読みの効きを YAML 内自己テストで担保するため必須．specs={pairs!r}"
    )
