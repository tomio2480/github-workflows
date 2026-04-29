"""templates/prh.yml の構造に対する回帰テスト．

prh は plain-string パターンを substring match するため，`JS` を裸で書くと
`JSON` 等に誤マッチする．JavaScript ルールの `JS` パターンは word-boundary 付き
regex `/\\bJS\\b/` で書く必要がある．
"""

from __future__ import annotations

import re
from pathlib import Path


_PRH_PATH = Path(__file__).resolve().parents[2] / "templates" / "prh.yml"


def test_javascript_rule_does_not_use_bare_js_pattern() -> None:
    content = _PRH_PATH.read_text(encoding="utf-8")
    bare_js_line = re.search(r"^\s*-\s*JS\s*$", content, re.MULTILINE)
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
