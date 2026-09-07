"""本リポジトリ自身の third-party action pin に対する回帰テスト．

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

走査と判定そのものは `scripts/check-action-pins.py` が持つ．caller リポジトリ
でも同じ検査が要るためである．本ファイルは，その判定を本リポジトリの実体へ
当てる役に絞る．判定の単体テストは `test_check_action_pins.py` にある．
"""

from __future__ import annotations

import fnmatch
import importlib
from pathlib import Path
from typing import Sequence

import pytest
import yaml


_MODULE = importlib.import_module("check-action-pins")
# 型注釈のために別名を置く．importlib 経由の取得は静的解析が追えないが，
# `from __future__ import annotations` により注釈は評価されないため成立する．
Pin = _MODULE.Pin

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def action_pins() -> list[Pin]:
    pins = _MODULE.collect_pins(_REPO_ROOT)
    assert pins, (
        "SHA pin を 1 件も収集できなかった．検索対象の glob か正規表現が"
        "実態と合っていない可能性がある．偽 green を避けるため fail させる．"
    )
    return pins


def test_pins_are_collected_from_templates_and_central(action_pins: list[Pin]) -> None:
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
    divergent = _MODULE.divergent_shas(action_pins)
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
    missing = _MODULE.pins_without_version(action_pins)
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
    malformed = _MODULE.pins_with_malformed_version(action_pins)
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
    ないと確かめられない．本テストはネットワークへ依存させないため，
    リポジトリ内部の一貫性だけを見る．手で写す際の取り違えはこれで捕まる．
    上流との突合は CI 側（`GITHUB_TOKEN` を持つ層）が担う．
    """
    inconsistent = _MODULE.inconsistent_versions(action_pins)
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


# Dependabot の走査範囲と pin 検査の走査範囲がずれていないかを見る（Issue #212）．
#
# `DEFAULT_GLOBS` は `.github/actions/**/action.yml` で入れ子まで pin 検査の
# 対象にする．一方 `.github/dependabot.yml` の `directories` が使えるワイルドカード
# は `*` だけである（GitHub の Dependabot options reference）．`*` は 1 階層しか
# 一致しないため，入れ子へ composite action を置くと **pin 検査は通るのに更新 PR は
# 来ない** 構成になる．誰も追随させない pin が生まれる．
#
# 範囲が揃っていることを規律ではなく機械で確かめる．ずれたら，入れ子をやめるか
# `dependabot.yml` へ当該ディレクトリを足すかを選ぶことになる．
_DEPENDABOT_CONFIG = _REPO_ROOT / ".github" / "dependabot.yml"


def _directory_matches(directory: str, pattern: str) -> bool:
    """`*` を 1 階層として扱い，ディレクトリが pattern に一致するかを返す．

    `fnmatch` をパス全体へ当てると `*` が `/` も飲み込み，1 階層しか一致しない
    という Dependabot の挙動を再現できない．区切りで分けて段ごとに当てる．
    """
    dir_parts = [part for part in directory.strip("/").split("/") if part]
    pattern_parts = [part for part in pattern.strip("/").split("/") if part]
    if len(dir_parts) != len(pattern_parts):
        return False
    return all(
        fnmatch.fnmatchcase(part, expected)
        for part, expected in zip(dir_parts, pattern_parts)
    )


def dependabot_action_directories() -> list[str]:
    """`github-actions` エコシステムの走査対象を先頭 `/` 付きで返す．"""
    document = yaml.safe_load(_DEPENDABOT_CONFIG.read_text(encoding="utf-8"))
    directories: list[str] = []
    for update in document["updates"]:
        if update["package-ecosystem"] != "github-actions":
            continue
        directories.extend(update.get("directories", []))
        if "directory" in update:
            directories.append(update["directory"])
    return directories


def composite_action_directories(root: Path) -> list[str]:
    """`.github/actions/` 配下の composite action を先頭 `/` 付きで返す．"""
    found: set[str] = set()
    for suffix in ("yml", "yaml"):
        for path in (root / ".github" / "actions").glob(f"**/action.{suffix}"):
            found.add("/" + path.parent.relative_to(root).as_posix())
    return sorted(found)


@pytest.mark.parametrize(
    ("directory", "covered"),
    [
        pytest.param("/.github/actions/markdown-lint", True, id="1 階層"),
        pytest.param("/.github/actions/group/nested", False, id="2 階層"),
        pytest.param("/", True, id="リポジトリ直下"),
    ],
)
def test_directory_matching_treats_star_as_one_level(
    directory: str, covered: bool
) -> None:
    """判定側が `*` を 1 階層として扱うこと．

    ここが `*` を貪欲に扱うと，入れ子も「走査対象に入っている」と読んでしまう．
    ずれの検出そのものが素通りするため，判定の性質を先に固定する．
    """
    patterns: Sequence[str] = ("/", "/.github/actions/*")

    assert (
        any(_directory_matches(directory, pattern) for pattern in patterns) is covered
    )


def test_every_composite_action_is_inside_dependabot_scan_range() -> None:
    """pin 検査の対象が Dependabot の走査範囲へ収まっていること（Issue #212）．

    外れた composite action の pin は，検査には掛かるが更新 PR が来ない．
    third-party action の SHA は Dependabot PR を通してのみ更新する運用のため，
    範囲から外れた時点で，その pin は誰も追随させない．
    """
    patterns = dependabot_action_directories()
    assert patterns, "dependabot.yml の github-actions に走査対象が無い"

    directories = composite_action_directories(_REPO_ROOT)
    # 収集が空だと「対象が無いので違反も無い」で通ってしまう．走査が壊れた
    # ときに指摘 0 件の成功へ化けるため，まず拾えていることを確かめる．
    assert directories, (
        "`.github/actions/` から composite action を 1 件も拾えなかった．"
        "収集の側が壊れている可能性がある．偽 green を避けるため fail させる．"
    )

    uncovered = [
        directory
        for directory in directories
        if not any(_directory_matches(directory, pattern) for pattern in patterns)
    ]

    assert not uncovered, "\n".join(
        [
            "Dependabot の走査範囲の外にある composite action がある．",
            "pin 検査は通るが更新 PR は来ない．入れ子をやめるか，",
            "`.github/dependabot.yml` の `directories` へ当該ディレクトリを足す．",
            *[f"  {directory}" for directory in uncovered],
        ]
    )
