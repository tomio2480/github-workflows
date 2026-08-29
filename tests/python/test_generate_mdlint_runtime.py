"""scripts/generate-mdlint-runtime.py の単体テスト．

仕様:
    - 引数は 2（src, dest）．それ以外のときは ValueError を上げる（誤用時の早期失敗）
    - 環境変数 GITHUB_OUTPUT が必須．未設定のときは ValueError を上げる
    - src に outputFormatters キーが無いときは dest を生成せず，
      GITHUB_OUTPUT へ `config=<src>` を追記する（パススルー）
    - src に outputFormatters キーがあるときは dest を生成してキーを除去し，
      GITHUB_OUTPUT へ `config=<dest>` を追記する
      （他のキーは保持する．値が null や空リストでもキーの存在だけで除去する）
    - 除去したときは '::warning::' で始まる警告を 1 行 stdout へ出す
    - 除去しなかったときは何も出力しない
    - src が空ファイル（YAML root が None）のときは dest を生成しない（パススルー）
    - src が存在しないときは FileNotFoundError が伝播する（fail-closed）
    - YAML root が mapping でないときは TypeError を上げる
    - dest の親ディレクトリが無ければ作成する
"""

import importlib
from pathlib import Path

import pytest
import yaml


# ハイフンを含むモジュール名は import 文で書けないため importlib で読み込む．
_MODULE = importlib.import_module("generate-mdlint-runtime")


@pytest.fixture
def github_output(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "github_output"
    path.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


def _write_yaml(path: Path, payload) -> Path:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def test_without_output_formatters_passes_src_through(
    tmp_path, capsys, github_output
):
    src = _write_yaml(
        tmp_path / "src.yaml", {"config": {"MD013": False}, "ignores": ["a/**"]}
    )
    dest = tmp_path / "out" / ".markdownlint-cli2.yaml"

    _MODULE.main([str(src), str(dest)])

    assert not dest.exists()
    assert github_output.read_text(encoding="utf-8") == f"config={src}\n"
    assert capsys.readouterr().out == ""


def test_with_output_formatters_key_is_removed_and_others_kept(
    tmp_path, github_output
):
    src = _write_yaml(
        tmp_path / "src.yaml",
        {
            "config": {"MD013": False, "MD041": True},
            "ignores": ["tests/fixtures/**"],
            "outputFormatters": [["markdownlint-cli2-formatter-json"]],
        },
    )
    dest = tmp_path / "out" / ".markdownlint-cli2.yaml"

    _MODULE.main([str(src), str(dest)])

    written = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert "outputFormatters" not in written
    assert written["config"] == {"MD013": False, "MD041": True}
    assert written["ignores"] == ["tests/fixtures/**"]
    assert github_output.read_text(encoding="utf-8") == f"config={dest}\n"


def test_removal_prints_single_warning_line(tmp_path, capsys, github_output):
    src = _write_yaml(tmp_path / "src.yaml", {"outputFormatters": []})
    dest = tmp_path / ".markdownlint-cli2.yaml"

    _MODULE.main([str(src), str(dest)])

    out_lines = capsys.readouterr().out.strip().splitlines()
    assert len(out_lines) == 1
    assert out_lines[0].startswith("::warning::")
    assert "outputFormatters" in out_lines[0]


def test_null_valued_key_is_also_removed(tmp_path, github_output):
    src = _write_yaml(tmp_path / "src.yaml", {"outputFormatters": None})
    dest = tmp_path / ".markdownlint-cli2.yaml"

    _MODULE.main([str(src), str(dest)])

    written = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert written == {}
    assert github_output.read_text(encoding="utf-8") == f"config={dest}\n"


def test_empty_src_file_passes_src_through(tmp_path, capsys, github_output):
    src = tmp_path / "src.yaml"
    src.write_text("", encoding="utf-8")
    dest = tmp_path / ".markdownlint-cli2.yaml"

    _MODULE.main([str(src), str(dest)])

    assert not dest.exists()
    assert github_output.read_text(encoding="utf-8") == f"config={src}\n"
    assert capsys.readouterr().out == ""


def test_missing_src_raises_file_not_found(tmp_path, github_output):
    dest = tmp_path / ".markdownlint-cli2.yaml"

    with pytest.raises(FileNotFoundError):
        _MODULE.main([str(tmp_path / "no-such.yaml"), str(dest)])


def test_non_mapping_root_raises_type_error(tmp_path, github_output):
    src = _write_yaml(tmp_path / "src.yaml", ["not", "a", "mapping"])
    dest = tmp_path / ".markdownlint-cli2.yaml"

    with pytest.raises(TypeError):
        _MODULE.main([str(src), str(dest)])


def test_dest_parent_directory_is_created(tmp_path, github_output):
    src = _write_yaml(tmp_path / "src.yaml", {"outputFormatters": []})
    dest = tmp_path / "deep" / "nested" / ".markdownlint-cli2.yaml"

    _MODULE.main([str(src), str(dest)])

    assert dest.is_file()


def test_missing_github_output_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    src = _write_yaml(tmp_path / "src.yaml", {})
    dest = tmp_path / ".markdownlint-cli2.yaml"

    with pytest.raises(ValueError):
        _MODULE.main([str(src), str(dest)])


@pytest.mark.parametrize("argv", [[], ["one"], ["a", "b", "c"]])
def test_wrong_argument_count_raises_value_error(argv, github_output):
    with pytest.raises(ValueError):
        _MODULE.main(argv)
