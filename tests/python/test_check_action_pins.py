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
    # `encoding` を明示する．`text=True` だけではロケール依存のデコードになり，
    # Windows（cp932）でローカル実行したとき日本語メッセージが化けるか
    # `UnicodeDecodeError` になる．検査は日本語の部分一致に依存している．
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
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


def test_collect_pins_covers_both_yaml_extensions(tmp_path: Path) -> None:
    """既定の走査が拡張子の双方と，composite action の入れ子へ届くこと．

    GitHub は workflow を `.yml` と `.yaml` の双方で認識し，composite action の
    定義ファイル名も `action.yml` と `action.yaml` の双方が有効である．片方だけを
    走査すると，もう片方へ置かれた pin がどの検査にも掛からない．検査は成功した
    まま素通りするため，失敗が沈黙する．走査の穴そのものをここで検査する．

    深さも同様である．composite action は任意のパスへ置けるため，
    `.github/actions/<group>/<name>/action.yml` は有効な構成である．
    `*` は 1 階層しか一致しないため，`**` で受ける．

    本テストが守るのは「`templates/` の pin が中央から取り残されないこと」
    （Issue #156）であって，「`.yml` かつ 1 階層の範囲で取り残されないこと」
    ではない．走査は，守ろうとしている条件と同じ広さで取る．

    切り出し（本 PR）で `DEFAULT_GLOBS` が狭まると，このテストが落ちる．
    元は `tests/python/test_action_pins.py` にあった検査を移設したものである
    （Issue #195・PR #199）．
    """
    line = pin_line("actions/checkout", _SHA_A, "v7.0.1")
    placements = (
        ".github/workflows/central.yml",
        ".github/workflows/central.yaml",
        ".github/actions/sample-yml/action.yml",
        ".github/actions/sample-yaml/action.yaml",
        ".github/actions/group/nested-yml/action.yml",
        ".github/actions/group/nested-yaml/action.yaml",
        "templates/.github/workflows/caller.yml",
        "templates/.github/workflows/caller.yaml",
    )
    for rel in (*placements, "templates/.github/workflows/caller.txt"):
        write_workflow(tmp_path, rel, [line])

    locations = {pin.location for pin in _MODULE.collect_pins(tmp_path)}

    assert locations == {f"{rel}:1" for rel in placements}, (
        f"収集の対象が想定と違う: {sorted(locations)}"
    )


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


def test_cli_fails_on_an_empty_scan_even_when_empty_is_permitted(
    tmp_path: Path,
) -> None:
    """走査対象が 0 件なら `--allow-empty` でも失敗させること．

    `Path.glob()` は存在しないディレクトリでも例外を出さず空を返す．
    そのため root の指定ミスと，pin を持たない正常な caller が，
    `--allow-empty` を付けた瞬間に同じ緑になる．
    「pin が 0 件」と「そもそも 1 つも読んでいない」は別の事象であり，
    後者は必ず落とす．
    """
    result = run_cli(tmp_path / "does-not-exist", "--allow-empty")

    assert result.returncode != 0
    assert "走査対象" in result.stderr


def test_cli_shortens_sha_in_the_inconsistent_version_message(
    tmp_path: Path,
) -> None:
    """同一 SHA の版表記ずれでも SHA を短縮して出すこと．

    pytest 経路のメッセージは 7 桁へ短縮している．CLI 経路だけ 40 桁の
    まま出ると，同じ違反が経路によって違う見え方になる．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, "v7.0.1")],
    )
    write_workflow(
        tmp_path,
        ".github/workflows/test.yml",
        [pin_line("actions/checkout", _SHA_A, "v7.0.2")],
    )

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert _SHA_A not in result.stderr, "SHA が短縮されずに出ている"
    assert _SHA_A[:7] in result.stderr


def test_cli_names_the_file_it_could_not_read(tmp_path: Path) -> None:
    """読めないファイルは，どれが原因かを示して落とすこと．

    生のトレースバックだけでは，caller リポジトリで原因のファイルを
    特定できない．
    """
    path = tmp_path / ".github" / "workflows" / "broken.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"uses: actions/checkout@" + b"\xff\xfe" * 4)

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert "broken.yml" in result.stderr


def unpinned_line(action: str, ref: str) -> str:
    return f"      uses: {action}@{ref}"


def test_collect_unpinned_reports_floating_refs(tmp_path: Path) -> None:
    """SHA で pin されていない remote 参照を拾うこと．

    `AGENTS.md` は「reusable workflow と third-party action は full commit SHA で
    pin する」と定める．`_USES_PIN` は 40 桁 SHA の行しか収集しないため，
    `@v7` のような浮動参照は pin としても違反としても現れず，検査を素通りする．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [unpinned_line("actions/checkout", "v7")],
    )

    unpinned = _MODULE.collect_unpinned(tmp_path)

    assert [(u.action, u.ref) for u in unpinned] == [("actions/checkout", "v7")]


def test_collect_unpinned_ignores_sha_pinned_refs(tmp_path: Path) -> None:
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [pin_line("actions/checkout", _SHA_A, "v7.0.1")],
    )

    assert _MODULE.collect_unpinned(tmp_path) == []


def test_collect_unpinned_ignores_local_action_references(tmp_path: Path) -> None:
    """`./` 始まりのローカル action は pin の対象外であること．"""
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        ["      uses: ./.github/actions/local"],
    )

    assert _MODULE.collect_unpinned(tmp_path) == []


def test_collect_unpinned_ignores_template_placeholders(tmp_path: Path) -> None:
    """配布テンプレの `@<SHA>` は浮動参照として扱わないこと．

    `templates/` は caller が置換して使う雛形である．山括弧を含む ref は
    git の参照として成立せず，未置換の目印であることが明らかである．
    これを違反として数えると，中央自身の自己検査が必ず落ちる．
    """
    write_workflow(
        tmp_path,
        "templates/.github/workflows/caller.yml",
        [unpinned_line("OWNER/github-workflows/.github/actions/x", "<SHA>")],
    )

    assert _MODULE.collect_unpinned(tmp_path) == []


def test_cli_fails_on_a_floating_ref_even_with_allow_empty(tmp_path: Path) -> None:
    """`--allow-empty` は浮動参照の存在を覆い隠さないこと．

    pin が 1 件も無い caller で `--allow-empty` を付けると，`@v7` のような
    参照だけを持つリポジトリが緑で通ってしまう．対象ファイルも third-party
    action も存在するのに，SHA pin の規律違反が偽 green になる形である．
    `--allow-empty` は remote 参照そのものが無い場合にだけ効かせる．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [unpinned_line("actions/checkout", "v7")],
    )

    result = run_cli(tmp_path, "--allow-empty")

    assert result.returncode != 0
    assert "actions/checkout" in result.stderr


def test_cli_fails_on_a_floating_ref_mixed_with_pinned_ones(tmp_path: Path) -> None:
    """pin が別にあっても，浮動参照は見逃さないこと．

    収集件数が非ゼロなら通る作りだと，1 件だけ SHA pin しておけば
    残りを浮動参照にできる．ゼロ件検査では捕まらない抜け道である．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [
            pin_line("actions/checkout", _SHA_A, "v7.0.1"),
            unpinned_line("actions/setup-node", "v4"),
        ],
    )

    result = run_cli(tmp_path)

    assert result.returncode != 0
    assert "actions/setup-node" in result.stderr


def test_cli_allows_empty_when_no_remote_reference_exists(tmp_path: Path) -> None:
    """remote 参照が 1 つも無い caller では `--allow-empty` が効くこと．"""
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        ["jobs:", "  a:", "    steps:", "      uses: ./.github/actions/local"],
    )

    result = run_cli(tmp_path, "--allow-empty")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("quote", ['"', "'"])
def test_collect_pins_captures_quoted_uses(quote: str, tmp_path: Path) -> None:
    """引用符で囲まれた `uses:` の pin も収集すること（Issue #211）．

    YAML は `uses: "owner/repo@<SHA>"` を同じ値として解釈する．
    GitHub Actions も同様である．収集から漏れると，同一 action の SHA 一致検査に
    も版コメントの検査にも掛からない．**検査は成功したまま素通りする．**
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [f"      uses: {quote}actions/checkout@{_SHA_A}{quote}"],
    )

    pins = _MODULE.collect_pins(tmp_path)

    assert [(p.action, p.sha) for p in pins] == [("actions/checkout", _SHA_A)]


@pytest.mark.parametrize("quote", ['"', "'"])
def test_collect_pins_captures_version_comment_after_a_quoted_pin(
    quote: str, tmp_path: Path
) -> None:
    """引用符の外に置いた版コメントを版として拾うこと（Issue #211）．

    版コメントは引用符の内側には入らない．閉じ引用符とコメントの境界を
    取り違えると，版が `None` になり「版コメントの無い pin」として誤って
    報告される．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [f"      uses: {quote}actions/checkout@{_SHA_A}{quote} # v7.0.1"],
    )

    pins = _MODULE.collect_pins(tmp_path)

    assert [p.version for p in pins] == ["v7.0.1"]


@pytest.mark.parametrize("quote", ['"', "'"])
def test_collect_unpinned_reports_quoted_floating_refs(
    quote: str, tmp_path: Path
) -> None:
    """引用符付きの浮動参照も違反として報告すること（Issue #211）．

    `_UNPINNED_USES` は先頭 1 文字を `[A-Za-z0-9_-]` に限る．ローカル action を
    外す意図だが，引用符も同時に外れる．違反が報告されないまま
    `AGENTS.md` の「full commit SHA で pin する」が素通りする．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [f"      uses: {quote}actions/checkout@v7{quote}"],
    )

    unpinned = _MODULE.collect_unpinned(tmp_path)

    assert [(u.action, u.ref) for u in unpinned] == [("actions/checkout", "v7")]


@pytest.mark.parametrize("quote", ['"', "'"])
def test_collect_unpinned_ignores_quoted_local_action_references(
    quote: str, tmp_path: Path
) -> None:
    """引用符を許しても，ローカル action は対象外のままであること．

    引用符の許容で `./` 始まりまで拾ってしまうと，上流を持たない参照を
    違反として数える．引用符の追加が別の誤検出を生んでいないことを確かめる．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [f"      uses: {quote}./.github/actions/local{quote}"],
    )

    assert _MODULE.collect_unpinned(tmp_path) == []


@pytest.mark.parametrize("quote", ['"', "'"])
def test_collect_unpinned_ignores_quoted_template_placeholders(
    quote: str, tmp_path: Path
) -> None:
    """引用符付きの未置換プレースホルダも違反として数えないこと．"""
    write_workflow(
        tmp_path,
        "templates/.github/workflows/caller.yml",
        [f"      uses: {quote}OWNER/github-workflows/.github/actions/x@<SHA>{quote}"],
    )

    assert _MODULE.collect_unpinned(tmp_path) == []


# `uses` の鍵が現れる書き方を列挙し，それぞれがどの区分へ入るかを固定する．
# 区分は `pin`（SHA pin として収集），`unpinned`（浮動参照として報告），
# `unrecognized`（形として認識できないと報告）の 3 つである．
# **どの区分にも入らない形** が「検査したのに何も検査していない」状態を作る．
_REMOTE_REFERENCE_FORMS = (
    ("bare-pin", f"      uses: actions/checkout@{_SHA_A}", "pin"),
    ("bare-float", "      uses: actions/checkout@v7", "unpinned"),
    ("double-quoted-pin", f'      uses: "actions/checkout@{_SHA_A}"', "pin"),
    ("double-quoted-float", '      uses: "actions/checkout@v7"', "unpinned"),
    ("single-quoted-pin", f"      uses: 'actions/checkout@{_SHA_A}'", "pin"),
    ("single-quoted-float", "      uses: 'actions/checkout@v7'", "unpinned"),
    ("list-element-pin", f"      - uses: actions/checkout@{_SHA_A}", "pin"),
    ("list-element-float", "      - uses: actions/checkout@v7", "unpinned"),
    (
        "quoted-pin-with-comment",
        f'      uses: "actions/checkout@{_SHA_A}" # v7.0.1',
        "pin",
    ),
    # ここから下は YAML としては成立するが，本リポジトリでは書かせない形である．
    # Dependabot が書き換えるのは `uses: <action>@<SHA> # vX.Y.Z` の 1 行だけで，
    # 下の形へ置くと版コメントの規律（Issue #157）が成立しない．
    # 収集できないまま放置せず，認識できない形として落とす．
    ("value-on-next-line", "      uses:", "unrecognized"),
    ("flow-mapping-pin", f"      - {{uses: actions/checkout@{_SHA_A}}}", "unrecognized"),
    ("flow-mapping-float", "      - {uses: actions/checkout@v7}", "unrecognized"),
    ("space-before-colon", f"      uses : actions/checkout@{_SHA_A}", "unrecognized"),
)


@pytest.mark.parametrize(
    ("label", "line", "expected"),
    _REMOTE_REFERENCE_FORMS,
    ids=[form[0] for form in _REMOTE_REFERENCE_FORMS],
)
def test_every_uses_form_falls_into_exactly_one_category(
    label: str, line: str, expected: str, tmp_path: Path
) -> None:
    """どの書き方も 3 区分のどれか 1 つへ必ず入ること（Issue #211）．

    正規表現で規律を検査する gate は，通り抜ける書き方を自分で列挙しないと
    穴に気づけない．本テストは書き方の一覧そのものを固定する．
    新しい書き方を許すときは，ここへ 1 行足してから実装を触る．
    """
    write_workflow(tmp_path, ".github/workflows/build.yml", [line])

    found = {
        "pin": len(_MODULE.collect_pins(tmp_path)),
        "unpinned": len(_MODULE.collect_unpinned(tmp_path)),
        "unrecognized": len(_MODULE.collect_unrecognized(tmp_path)),
    }

    assert sum(found.values()) == 1, (
        f"{label}: 区分が 1 つに定まらなかった（{found}）．"
        "0 なら検査を素通りしており，2 以上なら二重に数えている．"
    )
    assert found[expected] == 1, f"{label}: 想定と違う区分へ入った（{found}）"


def test_collect_unrecognized_ignores_uses_inside_comments(tmp_path: Path) -> None:
    """コメント中の `uses:` を認識できない形として数えないこと．

    実ファイルの comment は `uses:` の書き方そのものを説明する．
    コメントごと拾うと，正しく書かれたリポジトリが常に落ちる．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [
            "# Dependabot が追随するのは uses: の参照だけである．",
            f"      uses: actions/checkout@{_SHA_A} # v7.0.1",
            "      run: echo x # uses : ダミー",
        ],
    )

    assert _MODULE.collect_unrecognized(tmp_path) == []


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("      uses: ./.github/actions/local", id="ローカル action"),
        pytest.param("      uses: docker://alpine:3.22", id="docker 参照"),
        pytest.param("      houses: 3", id="uses を含む別の鍵"),
        pytest.param("      run: ./uses:x", id="鍵でない位置の uses:"),
    ],
)
def test_collect_unrecognized_ignores_out_of_scope_lines(
    line: str, tmp_path: Path
) -> None:
    """pin の規律の対象外を，認識できない形として数えないこと．

    ローカル action と docker 参照は上流の SHA を持たない．
    別の鍵や本文中の文字列を拾うと，誤検出でリポジトリが落ちる．
    """
    write_workflow(tmp_path, ".github/workflows/build.yml", [line])

    assert _MODULE.collect_unrecognized(tmp_path) == []


def test_collect_unrecognized_keeps_the_hash_inside_quotes(tmp_path: Path) -> None:
    """引用符の内側の `#` をコメントの開始として扱わないこと．

    切り出しを誤ると，行の残りが消えて `uses` の鍵ごと見えなくなる．
    見えなくなった行は認識できない形としても報告されず，素通りする．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        ['      - {uses: "actions/checkout@v7#frag"}'],
    )

    assert len(_MODULE.collect_unrecognized(tmp_path)) == 1


def test_collect_unrecognized_reports_unbalanced_quotes(tmp_path: Path) -> None:
    """開始と終了の引用符が対にならない行も報告すること．

    `_USES_PIN` と `_UNPINNED_USES` は後方参照で対を求めるため，対にならない行は
    どちらにも掛からない．YAML の二重引用符スカラーは複数行にまたがれるので，
    「対にならない ＝ 必ず不正な YAML」とは言えない．
    正しく解釈できないなら，解釈できないと報告する．
    """
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [f"      uses: \"actions/checkout@{_SHA_A}'"],
    )

    assert len(_MODULE.collect_unrecognized(tmp_path)) == 1


def test_cli_fails_on_an_unrecognized_uses_form(tmp_path: Path) -> None:
    """認識できない形があれば CLI が落ち，場所を名指しすること．"""
    write_workflow(
        tmp_path,
        ".github/workflows/build.yml",
        [
            "jobs:",
            "  a:",
            "    steps:",
            f"      - {{uses: actions/checkout@{_SHA_A}}}",
        ],
    )

    result = run_cli(tmp_path, "--allow-empty")

    assert result.returncode != 0
    assert ".github/workflows/build.yml:4" in result.stderr
