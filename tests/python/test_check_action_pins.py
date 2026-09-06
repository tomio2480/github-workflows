"""scripts/check-action-pins.py の単体テスト．

`tests/python/test_action_pins.py` は本リポジトリ自身の pin を検査する．
その走査と判定は caller リポジトリでも同じものが要る．
caller は `templates/` を持たず，中央の pytest も走らせないためである．

そこで走査と判定をスクリプトへ切り出し，root を引数で受け取れるようにする．
本テストは切り出した側の契約を固定する．検査対象は fixture として組み立て，
実在の `.github/` の中身へ依存させない．依存させると，リポジトリの都合で
検査が素通りしても気づけない．
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest


_MODULE = importlib.import_module("check-action-pins")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-action-pins.py"

_SHA_A = "0123456789abcdef0123456789abcdef01234567"
_SHA_B = "89abcdef0123456789abcdef0123456789abcdef"


def write_workflow(root: Path, relative: str, lines: list[str]) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def pin_line(action: str, sha: str, comment: str | None = "v1.2.3") -> str:
    suffix = "" if comment is None else f" # {comment}"
    return f"      uses: {action}@{sha}{suffix}"


def run_cli(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        capture_output=True,
        text=True,
    )


def test_collect_pins_reads_the_given_root_not_the_repository() -> None:
    """走査の起点は引数の root であること．

    実装が `Path(__file__)` からリポジトリルートを求めていると，caller の
    チェックアウトを渡しても中央の中身を読んでしまう．root を差し替えた
    ときに結果が変わることで，起点が引数側にあることを確かめる．
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_workflow(
            root,
            ".github/workflows/build.yml",
            ["jobs:", "  a:", "    steps:", pin_line("actions/checkout", _SHA_A)],
        )

        pins = _MODULE.collect_pins(root)

        assert [pin.action for pin in pins] == ["actions/checkout"]
        assert pins[0].sha == _SHA_A
        assert pins[0].version == "v1.2.3"
        assert pins[0].location == ".github/workflows/build.yml:4"


@pytest.mark.parametrize(
    ("comment", "expected_version"),
    [
        pytest.param(None, None, id="コメント無し"),
        pytest.param("v7.0.1", "v7.0.1", id="版のみ"),
        pytest.param(
            "actions/checkout v7.0.1",
            "actions/checkout v7.0.1",
            id="action 名付き",
        ),
        pytest.param(" v7.0.1  ", "v7.0.1", id="余分な空白"),
    ],
)
def test_collect_pins_captures_whole_trailing_comment(
    tmp_path: Path, comment: str | None, expected_version: str | None
) -> None:
    """行末コメントは空白を含んでいても丸ごと捕捉すること．

    版だけを `\\S+` で拾うと `# actions/checkout v7.0.1` のような複数トークンの
    コメントで行全体がマッチしなくなる．収集から漏れた pin は「版以外の記述」の
    検査にも「複数 SHA」の検査にも掛からず，検査そのものが素通りする．
    まさに Issue #157 が排除したい書き方が見逃される形であり，
    行末コメントは残り全体を捕捉する．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, comment)],
    )

    pins = _MODULE.collect_pins(tmp_path)

    assert len(pins) == 1, f"pin 行がマッチしない: コメント {comment!r}"
    assert pins[0].sha == _SHA_A
    assert pins[0].version == expected_version


def test_collect_pins_captures_list_element_form(tmp_path: Path) -> None:
    """`- uses:` のリスト要素形式も拾うこと．"""
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [f"      - uses: actions/checkout@{_SHA_A} # v7.0.1"],
    )

    assert len(_MODULE.collect_pins(tmp_path)) == 1


def test_collect_pins_skips_local_action_references(tmp_path: Path) -> None:
    """`./` 始まりのローカル action は pin の対象外であること．"""
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        ["    steps:", "      uses: ./.github/actions/local"],
    )

    assert _MODULE.collect_pins(tmp_path) == []


def test_collect_pins_accepts_explicit_globs(tmp_path: Path) -> None:
    """走査範囲を引数で差し替えられること．

    caller は `templates/` を持たない．既定の glob をそのまま押し付けず，
    呼び出し側が範囲を決められる形にする．
    """
    write_workflow(
        tmp_path,
        "custom/dir/flow.yml",
        [pin_line("actions/checkout", _SHA_A)],
    )

    assert _MODULE.collect_pins(tmp_path) == []
    assert len(_MODULE.collect_pins(tmp_path, ("custom/**/*.yml",))) == 1


def test_divergent_shas_reports_one_action_pinned_twice() -> None:
    pins = [
        _MODULE.Pin("actions/checkout", _SHA_A, "v1.2.3", "a.yml:1"),
        _MODULE.Pin("actions/checkout", _SHA_B, "v1.2.3", "b.yml:1"),
    ]

    divergent = _MODULE.divergent_shas(pins)

    assert set(divergent) == {"actions/checkout"}


def test_divergent_shas_accepts_one_action_pinned_once() -> None:
    pins = [
        _MODULE.Pin("actions/checkout", _SHA_A, "v1.2.3", "a.yml:1"),
        _MODULE.Pin("actions/checkout", _SHA_A, "v1.2.3", "b.yml:1"),
    ]

    assert _MODULE.divergent_shas(pins) == {}


def test_pins_without_version_lists_bare_pins() -> None:
    pins = [
        _MODULE.Pin("actions/checkout", _SHA_A, None, "a.yml:1"),
        _MODULE.Pin("actions/setup-node", _SHA_B, "v1.2.3", "b.yml:1"),
    ]

    assert [pin.location for pin in _MODULE.pins_without_version(pins)] == ["a.yml:1"]


@pytest.mark.parametrize(
    ("version", "malformed"),
    [
        pytest.param("v2", False, id="major のみ"),
        pytest.param("v2.19", False, id="minor まで"),
        pytest.param("v2.19.5", False, id="patch まで"),
        pytest.param("actions/checkout v7.0.1", True, id="action 名付き"),
        pytest.param("latest", True, id="版でない語"),
    ],
)
def test_pins_with_malformed_version_matches_dependabot_output(
    version: str, malformed: bool
) -> None:
    """版コメントは Dependabot が書き出す形（`# v7.0.1`）に限ること．"""
    pins = [_MODULE.Pin("actions/checkout", _SHA_A, version, "a.yml:1")]

    assert bool(_MODULE.pins_with_malformed_version(pins)) is malformed


def test_inconsistent_versions_reports_two_labels_for_one_sha() -> None:
    pins = [
        _MODULE.Pin("actions/checkout", _SHA_A, "v1.2.3", "a.yml:1"),
        _MODULE.Pin("actions/checkout", _SHA_A, "v1.2.4", "b.yml:1"),
    ]

    assert set(_MODULE.inconsistent_versions(pins)) == {_SHA_A}


def test_cli_exits_zero_for_a_clean_tree(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, "v7.0.1")],
    )

    result = run_cli(tmp_path)

    assert result.returncode == 0, result.stderr


def test_cli_lists_the_scanned_targets(tmp_path: Path) -> None:
    """検査した対象を標準出力へ残すこと．

    成功時に何も出さないと，走査が空振りした結果と区別が付かない．
    `github-dev` Skill の「検査対象をログへ残す」に対応する．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, "v7.0.1")],
    )

    result = run_cli(tmp_path)

    assert ".github/workflows/build.yml" in result.stdout


def test_cli_fails_when_one_action_has_two_shas(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, "v7.0.1")],
    )
    write_workflow(
        tmp_path,
        ".github/workflows/test.yml",
        [pin_line("actions/checkout", _SHA_B, "v7.0.1")],
    )

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert "actions/checkout" in result.stderr


def test_cli_fails_when_a_pin_has_no_version_comment(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, None)],
    )

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert ".github/workflows/build.yml:1" in result.stderr


def test_cli_fails_when_no_pin_is_found(tmp_path: Path) -> None:
    """1 件も拾えないときは成功で終わらせないこと．

    glob や正規表現が実態と合わなくなったとき，検査は「違反ゼロ」として
    緑で終わる．偽 green を避けるため，収集ゼロ自体を失敗として扱う．
    """
    write_workflow(tmp_path, ".github/workflows/build.yml", ["jobs: {}"])

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert "収集" in result.stderr


def test_cli_allows_empty_collection_when_explicitly_permitted(
    tmp_path: Path,
) -> None:
    """pin を持たない caller のために，空を許す入口を残すこと．

    既定は失敗のままにする．明示的に選んだときだけ緩める．
    """
    write_workflow(tmp_path, ".github/workflows/build.yml", ["jobs: {}"])

    result = run_cli(tmp_path, "--allow-empty")

    assert result.returncode == 0, result.stderr
