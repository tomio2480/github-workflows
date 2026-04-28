"""scripts/generate-textlint-runtime.py の単体テスト．

仕様:
    - rules.prh が dict のときは rulePaths を prh.yml の絶対パスに置換する
    - rules.prh が False または未定義のときはそのまま尊重する（書き換えない）
    - rules.prh がそれ以外の型のときは TypeError を上げる
    - rules 自体が dict でないときは TypeError を上げる
    - 引数が 3 つ未満のときは ValueError を上げる（誤用時の早期失敗）
"""

import importlib
import json
from pathlib import Path

import pytest


# ハイフンを含むモジュール名は import 文で書けないため importlib で読み込む．
_MODULE = importlib.import_module("generate-textlint-runtime")


def _write(path: Path, payload: dict) -> Path:
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

    with pytest.raises(TypeError, match="rules.prh"):
        _MODULE.main([str(src), str(prh), str(dest)])


def test_rules_not_object_raises_type_error(tmp_path):
    src = _write(tmp_path / "src.json", {"rules": ["not", "an", "object"]})
    prh = _make_prh(tmp_path)
    dest = tmp_path / "runtime.json"

    with pytest.raises(TypeError, match="rules"):
        _MODULE.main([str(src), str(prh), str(dest)])

@pytest.mark.parametrize("argv", [[], ["only-src"], ["src", "prh"]])
def test_too_few_arguments_raises_value_error(argv):
    with pytest.raises(ValueError, match="3"):
        _MODULE.main(argv)
