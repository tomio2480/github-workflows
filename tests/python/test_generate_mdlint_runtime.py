"""scripts/generate-mdlint-runtime.py の単体テスト．

仕様:
    - 引数は 1（src）．それ以外のときは ValueError を上げる（誤用時の早期失敗）
    - 環境変数 GITHUB_OUTPUT が必須．未設定のときは ValueError を上げる
    - src に outputFormatters キーが無いときは runtime を生成せず，
      GITHUB_OUTPUT へ `config=<src>` と `generated=`（空）を追記する（パススルー）
    - src に outputFormatters キーがあるときは src と同じディレクトリへ
      `.gh-workflows-runtime.markdownlint-cli2.yaml` を生成してキーを除去し，
      GITHUB_OUTPUT へ `config=<runtime>` と `generated=<runtime>` を追記する
      （他のキーは保持する．値が null や空リストでもキーの存在だけで除去する．
      同じディレクトリに置くのは config ファイル基準の相対パス解決
      （customRules / markdownItPlugins 等）を保つため）
    - 除去したときは '::warning::' で始まる警告を 1 行 stdout へ出す
    - 除去しなかったときは何も出力しない
    - src が空ファイル（YAML root が None）のときは生成しない（パススルー）
    - src が存在しないときは FileNotFoundError が伝播する（fail-closed）
    - YAML root が mapping でないときは TypeError を上げる
"""

import importlib
from pathlib import Path

import pytest
import yaml


# ハイフンを含むモジュール名は import 文で書けないため importlib で読み込む．
_MODULE = importlib.import_module("generate-mdlint-runtime")

RUNTIME_BASENAME = ".gh-workflows-runtime.markdownlint-cli2.yaml"


@pytest.fixture
def github_output(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "github_output"
    path.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


def _write_yaml(path: Path, payload) -> Path:
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def _outputs(github_output: Path) -> str:
    return github_output.read_text(encoding="utf-8")


def test_without_output_formatters_passes_src_through(
    tmp_path, capsys, github_output
):
    src = _write_yaml(
        tmp_path / "src.yaml", {"config": {"MD013": False}, "ignores": ["a/**"]}
    )

    _MODULE.main([str(src)])

    assert not (tmp_path / RUNTIME_BASENAME).exists()
    assert _outputs(github_output) == f"config={src}\ngenerated=\n"
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

    _MODULE.main([str(src)])

    runtime = tmp_path / RUNTIME_BASENAME
    written = yaml.safe_load(runtime.read_text(encoding="utf-8"))
    assert "outputFormatters" not in written
    assert written["config"] == {"MD013": False, "MD041": True}
    assert written["ignores"] == ["tests/fixtures/**"]
    assert _outputs(github_output) == f"config={runtime}\ngenerated={runtime}\n"


def test_runtime_is_created_beside_src(tmp_path, github_output):
    subdir = tmp_path / "nested"
    subdir.mkdir()
    src = _write_yaml(subdir / "src.yaml", {"outputFormatters": []})

    _MODULE.main([str(src)])

    assert (subdir / RUNTIME_BASENAME).is_file()


def test_removal_prints_single_warning_line(tmp_path, capsys, github_output):
    src = _write_yaml(tmp_path / "src.yaml", {"outputFormatters": []})

    _MODULE.main([str(src)])

    out_lines = capsys.readouterr().out.strip().splitlines()
    assert len(out_lines) == 1
    assert out_lines[0].startswith("::warning::")
    assert "outputFormatters" in out_lines[0]


def test_null_valued_key_is_also_removed(tmp_path, github_output):
    src = _write_yaml(tmp_path / "src.yaml", {"outputFormatters": None})

    _MODULE.main([str(src)])

    written = yaml.safe_load(
        (tmp_path / RUNTIME_BASENAME).read_text(encoding="utf-8")
    )
    assert written == {}


def test_empty_src_file_passes_src_through(tmp_path, capsys, github_output):
    src = tmp_path / "src.yaml"
    src.write_text("", encoding="utf-8")

    _MODULE.main([str(src)])

    assert not (tmp_path / RUNTIME_BASENAME).exists()
    assert _outputs(github_output) == f"config={src}\ngenerated=\n"
    assert capsys.readouterr().out == ""


def test_missing_src_raises_file_not_found(tmp_path, github_output):
    with pytest.raises(FileNotFoundError):
        _MODULE.main([str(tmp_path / "no-such.yaml")])


def test_non_mapping_root_raises_type_error(tmp_path, github_output):
    src = _write_yaml(tmp_path / "src.yaml", ["not", "a", "mapping"])

    with pytest.raises(TypeError):
        _MODULE.main([str(src)])


def test_missing_github_output_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    src = _write_yaml(tmp_path / "src.yaml", {})

    with pytest.raises(ValueError):
        _MODULE.main([str(src)])


@pytest.mark.parametrize("argv", [[], ["a", "b"]])
def test_wrong_argument_count_raises_value_error(argv, github_output):
    with pytest.raises(ValueError):
        _MODULE.main(argv)
