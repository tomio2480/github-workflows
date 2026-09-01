"""third-party action の pin と版コメントに対する回帰テスト．

`templates/` は Dependabot の走査対象へ入れられない．中央の
`.github/workflows/` と違い，caller 用の雛形であって本リポジトリの workflow
として実行されないためである．結果として `templates/` の pin だけが取り残され，
新規オンボーディングした caller が古い action から始まる状態が生じる．

Issue #156 では `templates/.github/workflows/md-lint.yml` の
`actions/checkout` が v4.3.1（2025-11-13）で止まり，中央側の v7.0.1 から
3 メジャー遅れていた．規律で追随させる運用は Issue #142 の経験どおり続かないため，
ずれを機械で検出する．

Issue #157 では版コメントの書き方を行末スタイルへ統一した．Dependabot は
SHA と同じ行のコメントだけを書き換える．直上行へ置いたコメントは更新されず，
レビューのたびに手で補正する工程が要る（PR #10 で実際に残置された）．
行末スタイルの強制と，同じ SHA に対する版表記の一貫性をここで検証する．
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]

# `uses: owner/repo@<40 桁 SHA>` と，あれば行末の版コメントを拾う．
# ローカル action（`./` 始まり）とタグ参照は対象外．タグ参照の禁止は
# 別の関心事であり本テストでは扱わない．
#
# コメントは空白を含みうるため残り全体を捕捉する．版だけを `\S+` で拾うと
# `# actions/checkout v7.0.1` の行がマッチせず，pin ごと収集から漏れる．
# 漏れた pin はどの検査にも掛からないため，検査が素通りする．
_USES_PIN = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<action>[\w.-]+/[\w.-]+(?:/[\w.-]+)*)"
    r"@(?P<sha>[0-9a-f]{40})"
    r"\s*(?:#\s*(?P<version>.*?))?\s*$"
)

# `docs/` は対象外とする（Issue #160）．`docs/development-notes.md` は
# Dependabot の挙動を示す証拠として PR #143 の差分を引いており，古い側の
# SHA と版が残っていることに意味がある．検査へ入れると直しようのない指摘に
# なる．オンボーディング手順（`docs/onboarding-new-repo.md`）も SHA を
# `git/refs/tags` から変数へ解決する形で，固定 SHA を書き下していない．
_SEARCH_GLOBS = (
    ".github/workflows/*.yml",
    ".github/actions/*/action.yml",
    "templates/**/*.yml",
)


_DUMMY_SHA = "0123456789abcdef0123456789abcdef01234567"


@dataclass(frozen=True)
class Pin:
    """1 箇所の SHA pin．`version` は行末コメントが無ければ None."""

    action: str
    sha: str
    version: str | None
    location: str


def _collect_pins() -> list[Pin]:
    pins: list[Pin] = []
    for pattern in _SEARCH_GLOBS:
        for path in sorted(_REPO_ROOT.glob(pattern)):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                matched = _USES_PIN.match(line)
                if matched is None:
                    continue
                pins.append(
                    Pin(
                        action=matched.group("action"),
                        sha=matched.group("sha"),
                        version=matched.group("version"),
                        location=f"{rel}:{lineno}",
                    )
                )
    return pins


@pytest.mark.parametrize(
    ("line", "expected_version"),
    [
        pytest.param(
            f"      uses: actions/checkout@{_DUMMY_SHA}",
            None,
            id="コメント無し",
        ),
        pytest.param(
            f"      uses: actions/checkout@{_DUMMY_SHA} # v7.0.1",
            "v7.0.1",
            id="版のみ",
        ),
        pytest.param(
            f"      - uses: actions/checkout@{_DUMMY_SHA} # v7.0.1",
            "v7.0.1",
            id="リスト要素",
        ),
        pytest.param(
            f"      uses: actions/checkout@{_DUMMY_SHA} # actions/checkout v7.0.1",
            "actions/checkout v7.0.1",
            id="action 名付き",
        ),
        pytest.param(
            f"      uses: actions/checkout@{_DUMMY_SHA}  #  v7.0.1  ",
            "v7.0.1",
            id="余分な空白",
        ),
    ],
)
def test_uses_pin_captures_whole_trailing_comment(
    line: str, expected_version: str | None
) -> None:
    """行末コメントは空白を含んでいても丸ごと捕捉すること．

    版だけを `\\S+` で拾うと `# actions/checkout v7.0.1` のような複数トークンの
    コメントで行全体がマッチしなくなる．収集から漏れた pin は「版以外の記述」の
    検査にも「複数 SHA」の検査にも掛からず，検査そのものが素通りする．
    まさに Issue #157 が排除したい書き方が見逃される形であり，
    行末コメントは残り全体を捕捉する．
    """
    matched = _USES_PIN.match(line)
    assert matched is not None, f"pin 行がマッチしない: {line!r}"
    assert matched.group("sha") == _DUMMY_SHA
    assert matched.group("version") == expected_version


@pytest.fixture(scope="module")
def action_pins() -> list[Pin]:
    pins = _collect_pins()
    assert pins, (
        "SHA pin を 1 件も収集できなかった．検索対象の glob か正規表現が"
        "実態と合っていない可能性がある．偽 green を避けるため fail させる．"
    )
    return pins


def test_pins_are_collected_from_templates_and_central(
    action_pins: list[Pin],
) -> None:
    """収集が `templates/` と中央の双方へ届いていることを確認する．

    どちらか片方しか読めていないと，ずれの検査そのものが成立しない．
    """
    locations = [pin.location for pin in action_pins]
    assert any(loc.startswith("templates/") for loc in locations), (
        "templates/ 配下から SHA pin を収集できていない．検索 glob を確認すること．"
    )
    assert any(loc.startswith(".github/") for loc in locations), (
        ".github/ 配下から SHA pin を収集できていない．検索 glob を確認すること．"
    )


def test_same_action_is_pinned_to_one_sha(action_pins: list[Pin]) -> None:
    """同じ action がリポジトリ内で 2 つ以上の SHA を指していないこと．

    意図的に版を分けたい事情が生じた場合は，本テストを緩めるのではなく
    なぜ分けるのかを判断記録へ残したうえで除外リストを設けること．
    """
    by_action: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for pin in action_pins:
        by_action[pin.action][pin.sha].append(pin.location)

    divergent = {action: shas for action, shas in by_action.items() if len(shas) > 1}
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


def test_every_pin_has_trailing_version_comment(action_pins: list[Pin]) -> None:
    """すべての pin が行末に版コメントを持つこと．

    Dependabot が自動で書き換えるのは SHA と同じ行のコメントだけである．
    直上行へ置くと SHA だけが更新され，版表記が古いまま残る．
    """
    missing = [pin for pin in action_pins if pin.version is None]
    assert not missing, "\n".join(
        [
            "行末の版コメントが無い pin がある．"
            "`uses: <action>@<SHA> # vX.Y.Z` の形へ揃えること．"
            "直上行のコメントは Dependabot が更新しない（Issue #157）．",
            *[f"  {pin.location}: {pin.action}@{pin.sha[:7]}" for pin in missing],
        ]
    )


def test_version_comment_looks_like_a_version(action_pins: list[Pin]) -> None:
    """版コメントが `vX`〜`vX.Y.Z` 形式であること．

    Dependabot が書き出すのは版だけである（`# v7.0.1`）．action 名を添えた
    `# actions/checkout v7.0.1` 形式を残すと，自動更新の結果と混在する．
    """
    version_pattern = re.compile(r"^v\d+(?:\.\d+){0,2}$")
    malformed = [
        pin
        for pin in action_pins
        if pin.version is not None and not version_pattern.match(pin.version)
    ]
    assert not malformed, "\n".join(
        [
            "版コメントが版だけの形になっていない．"
            "Dependabot の出力（`# v7.0.1`）へ合わせること．",
            *[f"  {pin.location}: `# {pin.version}`" for pin in malformed],
        ]
    )


def test_same_sha_has_consistent_version_comment(action_pins: list[Pin]) -> None:
    """同じ SHA に対して 2 通りの版表記が書かれていないこと．

    SHA と版の対応そのもの（当該 SHA が本当に v7.0.1 か）は上流へ問い合わせ
    ないと確かめられない．CI をネットワークへ依存させないため，ここでは
    リポジトリ内部の一貫性だけを見る．手で写す際の取り違えはこれで捕まる．
    """
    by_sha: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for pin in action_pins:
        if pin.version is not None:
            by_sha[pin.sha][pin.version].append(pin.location)

    inconsistent = {
        sha: versions for sha, versions in by_sha.items() if len(versions) > 1
    }
    assert not inconsistent, "\n".join(
        [
            "同じ SHA へ異なる版コメントが書かれている．どちらかが誤りである．",
            *[
                f"  {sha[:7]}: "
                + " / ".join(
                    f"`# {version}` ({', '.join(locations)})"
                    for version, locations in sorted(versions.items())
                )
                for sha, versions in sorted(inconsistent.items())
            ],
        ]
    )
