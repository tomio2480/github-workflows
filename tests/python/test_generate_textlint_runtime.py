"""scripts/generate-textlint-runtime.py の単体テスト．

仕様:
    - rules.prh が dict のときは rulePaths を prh.yml の絶対パスに置換する
    - rules.prh が False または未定義のときはそのまま尊重する（書き換えない）
    - rules.prh がそれ以外の型のときは TypeError を上げる
    - rules 自体が dict でないときは TypeError を上げる
    - 引数は 3 または 4．それ以外のときは ValueError を上げる（誤用時の早期失敗）
    - argv 4 つ目（allowlist YAML パス）が空文字のときは filters を変更しない
    - argv 4 つ目が valid なファイルのときは内容を filters.allowlist に inject する
    - argv 4 つ目が指定されたが存在しないファイルのときは ValueError
    - allowlist YAML root が dict でないときは TypeError
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
        ["src", "prh", "dest", "allowlist", "extra"],
    ],
)
def test_argv_must_be_3_or_4_otherwise_value_error(argv):
    with pytest.raises(ValueError, match=r"3 or 4"):
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
        "allow:\n  - 電波法施行規則\nallowRules:\n  - ja-technical-writing/ja-no-mixed-period\n",
    )

    _MODULE.main([str(src), str(prh), str(dest), str(allowlist)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["filters"]["allowlist"] == {
        "allow": ["電波法施行規則"],
        "allowRules": ["ja-technical-writing/ja-no-mixed-period"],
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


# ── overrides 内の prh.rulePaths 解決 ──────────────────────────────────────


def test_overrides_prh_rulepaths_resolved_to_absolute(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {
            "rules": {},
            "overrides": [
                {
                    "files": ["claude/agents/**/*.md"],
                    "rules": {
                        "prh": {"rulePaths": ["./prh.yml"]},
                        "preset-ja-technical-writing": {
                            "no-mix-dearu-desumasu": {
                                "preferInBody": "ですます",
                                "preferInList": "ですます",
                            }
                        },
                    },
                }
            ],
        },
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    override_prh = written["overrides"][0]["rules"]["prh"]
    assert override_prh["rulePaths"] == [str(prh.resolve())]


def test_overrides_without_prh_preserved(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {
            "rules": {},
            "overrides": [
                {
                    "files": ["claude/agents/**/*.md"],
                    "rules": {
                        "preset-ja-technical-writing": {
                            "no-mix-dearu-desumasu": {"preferInBody": "ですます"}
                        }
                    },
                }
            ],
        },
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    override_rules = written["overrides"][0]["rules"]
    assert "prh" not in override_rules
    assert override_rules["preset-ja-technical-writing"]["no-mix-dearu-desumasu"] == {
        "preferInBody": "ですます"
    }


def test_overrides_absent_no_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {}})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert "overrides" not in written


def test_overrides_empty_list_no_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": {}, "overrides": []})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["overrides"] == []


def test_overrides_prh_false_preserved(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {
            "rules": {},
            "overrides": [
                {
                    "files": ["docs/**/*.md"],
                    "rules": {"prh": False},
                }
            ],
        },
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    _MODULE.main([str(src), str(prh), str(dest)])

    written = json.loads(dest.read_text(encoding="utf-8"))
    assert written["overrides"][0]["rules"]["prh"] is False


def test_overrides_prh_unsupported_type_raises_type_error(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {
            "rules": {},
            "overrides": [
                {
                    "files": ["docs/**/*.md"],
                    "rules": {"prh": "string-not-allowed"},
                }
            ],
        },
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match=r"overrides\[0\]\.rules\.prh"):
        _MODULE.main([str(src), str(prh), str(dest)])


def test_overrides_not_list_raises_type_error(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {}, "overrides": {"files": ["**/*.md"], "rules": {}}},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match=r"'overrides' must be an array"):
        _MODULE.main([str(src), str(prh), str(dest)])


def test_overrides_entry_not_dict_raises_type_error(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {"rules": {}, "overrides": ["not-a-dict"]},
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match=r"overrides\[0\]' must be an object"):
        _MODULE.main([str(src), str(prh), str(dest)])


def test_overrides_entry_rules_not_dict_raises_type_error(tmp_path):
    src = _write(
        tmp_path / "src.json",
        {
            "rules": {},
            "overrides": [{"files": ["**/*.md"], "rules": "not-a-dict"}],
        },
    )
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match=r"overrides\[0\]\.rules' must be an object"):
        _MODULE.main([str(src), str(prh), str(dest)])