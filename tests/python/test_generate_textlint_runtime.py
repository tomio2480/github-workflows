"""scripts/generate-textlint-runtime.py の単体テスト．

仕様:
    - rules.prh が dict のときは rulePaths を prh.yml の絶対パスに置換する
    - rules.prh が False または未定義のときはそのまま尊重する（書き換えない）
    - rules.prh がそれ以外の型のときは TypeError を上げる
    - rules 自体が dict でないときは TypeError を上げる
    - 引数は 3〜5．それ以外のときは ValueError を上げる（誤用時の早期失敗）
    - argv 4 つ目（allowlist YAML パス）が空文字のときは filters を変更しない
    - argv 4 つ目が valid なファイルのときは内容を filters.allowlist に inject する
    - argv 4 つ目が指定されたが存在しないファイルのときは ValueError
    - allowlist YAML root が dict でないときは TypeError
    - allowlist に allow / allowlistConfigPaths 以外の鍵があると警告を出す
      （内容は書き換えず素通しする．Issue #98）
    - argv 5 つ目（caller 追加 prh 辞書パス）が空文字または省略のときは rulePaths は 1 本
    - argv 5 つ目が valid なファイルのときは rulePaths を [中央, 追加] の 2 本にする
    - argv 5 つ目が指定されたが存在しないファイルのときは ValueError
    - rules.prh が False / 未定義なら argv 5 つ目があっても書き換えない
    - JSON ルートが dict でないときは ValueError を上げる
"""

import importlib
import json
from pathlib import Path

import pytest


# ハイフンを含むモジュール名は import 文で書けないため importlib で読み込む．
_MODULE = importlib.import_module("generate-textlint-runtime")


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _make_prh(tmp_path: Path) -> Path:
    prh = tmp_path / "prh.yml"
    prh.write_text("version: 1\nrules: []\n", encoding="utf-8")
    return prh


def test_prh_dict_rulepaths_is_replaced_with_absolute_path(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {"prh": {"rulePaths": ["./relative.yml"]}}},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    rule_paths = written["rules"]["prh"]["rulePaths"]
    assert rule_paths == [str(prh.resolve())]


def test_prh_false_is_kept_as_false(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {"prh": False}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["rules"]["prh"] is False


def test_prh_missing_does_not_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {"other-rule": True}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert "prh" not in written["rules"]
    assert written["rules"]["other-rule"] is True


def test_prh_unsupported_type_raises_type_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {"prh": "string-not-allowed"}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match=r"rules\.prh"):
        _MODULE.main([str(src), str(prh), str(dest)])


def test_rules_not_object_raises_type_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": ["not", "an", "object"]})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match="rules"):
        _MODULE.main([str(src), str(prh), str(dest)])


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["only-src"],
        ["src", "prh"],
        ["src", "prh", "dest", "allowlist", "prh-extra", "too-many"],
    ],
)
def test_argv_must_be_3_to_5_otherwise_value_error(argv):
    with pytest.raises(ValueError, match=r"3 to 5"):
        _MODULE.main(argv)


@pytest.mark.parametrize(
    "non_dict_cfg",
    [
        [],
        ["a", "list"],
        "a-string",
        42,
        None,
    ],
)
def test_json_root_must_be_object_otherwise_value_error(tmp_path, non_dict_cfg):
    src = _write(tmp_path / "src.json", non_dict_cfg)
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(ValueError, match="object"):
        _MODULE.main([str(src), str(prh), str(dest)])


def _make_allowlist(tmp_path: Path, body: str) -> Path:
    allowlist = tmp_path / "allowlist.yml"
    allowlist.write_text(body, encoding="utf-8")
    return allowlist


def test_allowlist_dict_is_injected_into_filters(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {}, "filters": {"allowlist": {}, "comments": True}},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(
        tmp_path,
        "allow:\n  - 電波法施行規則\n  - '/(?<=^[表図] [0-9]+[.] .*)[^．]$/m'\n",
    )

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["filters"]["allowlist"] == {
        "allow": ["電波法施行規則", "/(?<=^[表図] [0-9]+[.] .*)[^．]$/m"],
    }
    # 既存の他 filter（comments）は維持される
    assert written["filters"]["comments"] is True


def test_allowlist_empty_dict_is_injected_as_noop(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {}, "filters": {"allowlist": {"allow": ["legacy"]}}},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(tmp_path, "{}\n")

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    # 空の allowlist で上書きされる（caller が「何も許容しない」 と意図したケース）
    assert written["filters"]["allowlist"] == {}


def test_allowlist_path_empty_string_does_not_modify_filters(tmp_path):
    original_filters = {"allowlist": {"allow": ["preserve-me"]}, "comments": True}
    src = _write(
        tmp_path / "src.json",
        {"rules": {}, "filters": dict(original_filters)},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest), ""])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["filters"] == original_filters


def test_allowlist_creates_filters_when_absent(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(tmp_path, "allow:\n  - 固有名詞\n")

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["filters"]["allowlist"] == {"allow": ["固有名詞"]}


def test_allowlist_missing_file_raises_value_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    missing = tmp_path / "does-not-exist.yml"

    with pytest.raises(ValueError, match="allowlist"):
        _MODULE.main([str(src), str(prh), str(dest), str(missing)])


@pytest.mark.parametrize(
    "yaml_body",
    [
        "- a\n- b\n",
        "just a string\n",
        "42\n",
    ],
)
def test_allowlist_root_must_be_dict_otherwise_type_error(tmp_path, yaml_body):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(tmp_path, yaml_body)

    with pytest.raises(TypeError, match="allowlist"):
        _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])


def test_allowlist_unknown_key_emits_github_warning(tmp_path, capsys):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(tmp_path, "allowRules:\n  - some-rule\n")

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    out = capsys.readouterr().out
    assert out.startswith("::warning::")
    assert "allowRules" in out
    # 警告のみで挙動は変えない．内容はそのまま inject する（素通し）
    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["filters"]["allowlist"] == {"allowRules": ["some-rule"]}


def test_allowlist_multiple_unknown_keys_are_all_listed(tmp_path, capsys):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(
        tmp_path, "allow:\n  - foo\nallowRules:\n  - bar\ntypo: true\n"
    )

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    out = capsys.readouterr().out
    assert "allowRules" in out
    assert "typo" in out
    assert "allow" in out  # 警告文には有効な鍵の案内も含める


def test_allowlist_known_keys_only_no_warning(tmp_path, capsys):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(
        tmp_path, "allow:\n  - foo\nallowlistConfigPaths:\n  - ./extra.yml\n"
    )

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "non_dict_filters",
    [
        None,
        False,
        [],
        ["a", "list"],
        "string",
        42,
    ],
)
def test_allowlist_filters_non_dict_raises_type_error(tmp_path, non_dict_filters):
    """既存 filters が dict でない場合は意図的に TypeError を上げる（fail-fast）．

    rules の strict ハンドリングと整合する設計．caller が `"filters": null` や
    `"filters": false` と明示している場合は silent overwrite せず caller 意図を尊重する．
    """
    src = _write(
        tmp_path / "src.json",
        {"rules": {}, "filters": non_dict_filters},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    allowlist = _make_allowlist(tmp_path, "allow:\n  - foo\n")

    with pytest.raises(TypeError, match="filters"):
        _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])


# ── caller 追加 prh 辞書（.prh-extra.yml）は中央辞書に加算する（Issue #91）─────
# textlint-rule-prh は rulePaths を配列で受け，同一パターンの衝突は先に並べた辞書が
# 勝つ（v6.1.0 で実測）．中央を先頭に置き，caller は語を「足す」だけにする．


def _make_prh_extra(tmp_path: Path) -> Path:
    extra = tmp_path / ".prh-extra.yml"
    extra.write_text(
        "version: 1\nrules:\n  - expected: ，\n    patterns:\n      - 、\n",
        encoding="utf-8",
    )
    return extra


def test_prh_extra_appends_after_central_dictionary(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {"prh": {"rulePaths": ["./relative.yml"]}}},
    )
    prh = _make_prh(tmp_path)
    extra = _make_prh_extra(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest), "", str(extra)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["rules"]["prh"]["rulePaths"] == [
        str(prh.resolve()),
        str(extra.resolve()),
    ]


def test_prh_extra_empty_string_keeps_single_rulepath(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {"prh": {"rulePaths": ["./relative.yml"]}}},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest), "", ""])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["rules"]["prh"]["rulePaths"] == [str(prh.resolve())]


def test_prh_extra_can_combine_with_allowlist(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {"prh": {"rulePaths": ["./relative.yml"]}}, "filters": {}},
    )
    prh = _make_prh(tmp_path)
    extra = _make_prh_extra(tmp_path)
    allowlist = _make_allowlist(tmp_path, "allow:\n  - 固有名詞\n")
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist), str(extra)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["rules"]["prh"]["rulePaths"] == [
        str(prh.resolve()),
        str(extra.resolve()),
    ]
    assert written["filters"]["allowlist"] == {"allow": ["固有名詞"]}


def test_prh_extra_missing_file_raises_value_error(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {"prh": {"rulePaths": ["./relative.yml"]}}},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"
    missing = tmp_path / "does-not-exist.yml"

    with pytest.raises(ValueError, match="prh"):
        _MODULE.main([str(src), str(prh), str(dest), "", str(missing)])


@pytest.mark.parametrize("prh_value", [False, None])
def test_prh_extra_is_ignored_when_prh_disabled_or_missing(tmp_path, prh_value):
    rules = {"other-rule": True}
    if prh_value is False:
        rules["prh"] = False
    src = _write(tmp_path / "src.json", {"rules": rules})
    prh = _make_prh(tmp_path)
    extra = _make_prh_extra(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest), "", str(extra)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["rules"].get("prh") is prh_value


# ── overrides は textlint 未実装のため素通し + 警告 ──────────────────────────
# textlint 15.6.0 の @textlint/config-loader は plugins / filters / rules のみを読む．
# overrides は無視されるため，本スクリプトも中身を書き換えず，
# caller へ ::warning:: アノテーションで「効いていない」ことを知らせる（Issue #85）．


def _src_with_overrides(tmp_path):
    return _write(
        tmp_path / "src.json",
        {
            "rules": {"prh": {"rulePaths": ["./prh.yml"]}},
            "overrides": [
                {
                    "files": ["claude/agents/**/*.md"],
                    "rules": {
                        "prh": {"rulePaths": ["./prh.yml"]},
                        "preset-ja-technical-writing": {
                            "no-mix-dearu-desumasu": {"preferInBody": "ですます"}
                        },
                    },
                }
            ],
        },
    )


def test_overrides_passed_through_untouched(tmp_path):
    src = _src_with_overrides(tmp_path)
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    # top-level rules.prh は従来どおり絶対パスへ解決される
    assert written["rules"]["prh"]["rulePaths"] == [str(prh.resolve())]
    # overrides は一切書き換えない（相対パスのまま，構造も保持）
    assert written["overrides"] == json.loads(src.read_text(encoding="utf-8"))["overrides"]


def test_overrides_present_emits_github_warning(tmp_path, capsys):
    src = _src_with_overrides(tmp_path)
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    out = capsys.readouterr().out
    assert out.startswith("::warning::")
    assert "overrides" in out
    assert "textlint" in out


def test_overrides_absent_no_warning(tmp_path, capsys):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert "overrides" not in written
    assert capsys.readouterr().out == ""


def test_overrides_empty_list_no_warning(tmp_path, capsys):
    src = _write(tmp_path / "src.json", {"rules": {}, "overrides": []})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["overrides"] == []
    assert capsys.readouterr().out == ""
