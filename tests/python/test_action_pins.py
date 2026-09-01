"""third-party action の pin がリポジトリ全体で一致することを検査する．

`templates/` は Dependabot の走査対象へ入れられない．中央の
`.github/workflows/` と違い，caller 用の雛形であって本リポジトリの workflow
として実行されないためである．結果として `templates/` の pin だけが取り残され，
新規オンボーディングした caller が古い action から始まる状態が生じる．

Issue #156 では `templates/.github/workflows/md-lint.yml` の
`actions/checkout` が v4.3.1（2025-11-13）で止まり，中央側の v7.0.1 から
3 メジャー遅れていた．規律で追随させる運用は Issue #142 の経験どおり続かないため，
ずれを機械で検出する．
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]

# `uses: owner/repo@<40 桁 SHA>` を拾う．ローカル action（`./` 始まり）と
# タグ参照は対象外．タグ参照の禁止は別の関心事であり本テストでは扱わない．
_USES_PIN = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<action>[\w.-]+/[\w.-]+(?:/[\w.-]+)*)"
    r"@(?P<sha>[0-9a-f]{40})"
)

_SEARCH_GLOBS = (
    ".github/workflows/*.yml",
    ".github/actions/*/action.yml",
    "templates/**/*.yml",
)


def _collect_pins() -> dict[str, dict[str, list[str]]]:
    """action 名ごとに `SHA -> 出現箇所` の対応を集める．"""
    pins: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for pattern in _SEARCH_GLOBS:
        for path in sorted(_REPO_ROOT.glob(pattern)):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                matched = _USES_PIN.match(line)
                if matched is None:
                    continue
                action = matched.group("action")
                pins[action][matched.group("sha")].append(f"{rel}:{lineno}")
    return pins


@pytest.fixture(scope="module")
def action_pins() -> dict[str, dict[str, list[str]]]:
    pins = _collect_pins()
    assert pins, (
        "SHA pin を 1 件も収集できなかった．検索対象の glob か正規表現が"
        "実態と合っていない可能性がある．偽 green を避けるため fail させる．"
    )
    return pins


def test_pins_are_collected_from_templates_and_central(
    action_pins: dict[str, dict[str, list[str]]],
) -> None:
    """収集が `templates/` と中央の双方へ届いていることを確認する．

    どちらか片方しか読めていないと，ずれの検査そのものが成立しない．
    """
    locations = [
        location
        for shas in action_pins.values()
        for occurrences in shas.values()
        for location in occurrences
    ]
    assert any(loc.startswith("templates/") for loc in locations), (
        "templates/ 配下から SHA pin を収集できていない．検索 glob を確認すること．"
    )
    assert any(loc.startswith(".github/") for loc in locations), (
        ".github/ 配下から SHA pin を収集できていない．検索 glob を確認すること．"
    )


def test_same_action_is_pinned_to_one_sha(
    action_pins: dict[str, dict[str, list[str]]],
) -> None:
    """同じ action がリポジトリ内で 2 つ以上の SHA を指していないこと．

    意図的に版を分けたい事情が生じた場合は，本テストを緩めるのではなく
    なぜ分けるのかを判断記録へ残したうえで除外リストを設けること．
    """
    divergent = {action: shas for action, shas in action_pins.items() if len(shas) > 1}
    assert not divergent, "\n".join(
        [
            "同じ action が複数の SHA へ pin されている．"
            "templates/ は Dependabot の走査対象外のため取り残されやすい．",
            *[
                f"  {action}: "
                + " / ".join(
                    f"{sha[:7]} ({', '.join(locations)})"
                    for sha, locations in sorted(shas.items())
                )
                for action, shas in sorted(divergent.items())
            ],
        ]
    )
