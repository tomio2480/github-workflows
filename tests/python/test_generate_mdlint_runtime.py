"""scripts/generate-mdlint-runtime.py の単体テスト．

仕様:
    - 引数は 1（src）．それ以外のときは ValueError を上げる（誤用時の早期失敗）
    - 環境変数 GITHUB_OUTPUT が必須．未設定のときは ValueError を上げる
    - src に outputFormatters キーが無いときは runtime を生成せず，
      GITHUB_OUTPUT へ `config=<src>` と `generated=`（空）を追記する（パススルー）
    - src に outputFormatters キーがあるときは src と同じディレクトリへ
      `.gh-workflows-runtime-*.markdownlint-cli2.yaml` の一意名で生成し，
      GITHUB_OUTPUT へ `config=<runtime>` と `generated=<runtime>` を追記する
      （一意名は既存ファイルと衝突しない．caller 所有ファイルを上書きしない）
    - 除去はトップレベルキーのテキスト除去で行い，他の行はバイト単位で保持する
      （PyYAML の YAML 1.1 往復による型崩れ（on / yes の bool 化等）を避ける．
      PyYAML は検出・検証のみに使う）
    - block style・flow style（1 行値）・引用符付きキーのいずれも除去できる
    - root mapping が一様にインデントされていても，そのインデントを検出して
      照合・消費する（列 0 固定にしない）
    - インデントなしの block sequence（列 0 の `- ` エントリ）も値として消費する
    - 消費中の列 0 コメント行（`#` 始まり）は読み飛ばす（コメント除去は
      runtime の意味を変えない）
    - UTF-8 BOM 付きの src も受理する（utf-8-sig で読む．生成物は BOM なし）
    - 生成物は parse し直し，root のキー集合が「元 − outputFormatters」と
      一致することを検証する（壊れた runtime を黙って渡さない）
    - 検出はできたがテキスト除去でキー行を特定できないとき（flow style の
      root mapping 等）は ValueError を上げる（fail-closed．黙って型崩れさせない）
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

RUNTIME_PREFIX = ".gh-workflows-runtime-"
RUNTIME_SUFFIX = ".markdownlint-cli2.yaml"


@pytest.fixture
def github_output(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "github_output"
    path.touch()
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    return path


def _outputs(github_output: Path) -> dict:
    pairs = [
        line.split("=", 1)
        for line in github_output.read_text(encoding="utf-8").splitlines()
    ]
    return {key: value for key, value in pairs}


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_without_output_formatters_passes_src_through(
    tmp_path, capsys, github_output
):
    src = _write(
        tmp_path / "src.yaml", "config:\n  MD013: false\nignores:\n  - a/**\n"
    )

    _MODULE.main([str(src)])

    assert list(tmp_path.glob(f"{RUNTIME_PREFIX}*")) == []
    assert _outputs(github_output) == {"config": str(src), "generated": ""}
    assert capsys.readouterr().out == ""


def test_block_style_key_is_removed_and_other_lines_kept_verbatim(
    tmp_path, github_output
):
    src = _write(
        tmp_path / "src.yaml",
        "config:\n"
        "  MD013: false\n"
        "outputFormatters:\n"
        "  - [markdownlint-cli2-formatter-json]\n"
        "ignores:\n"
        "  - tests/fixtures/**\n",
    )

    _MODULE.main([str(src)])

    outputs = _outputs(github_output)
    runtime = Path(outputs["generated"])
    assert runtime.read_text(encoding="utf-8") == (
        "config:\n  MD013: false\nignores:\n  - tests/fixtures/**\n"
    )
    assert outputs["config"] == str(runtime)


def test_flow_style_single_line_value_is_removed(tmp_path, github_output):
    src = _write(
        tmp_path / "src.yaml",
        "outputFormatters: [[markdownlint-cli2-formatter-json]]\n"
        "config:\n"
        "  MD041: true\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "config:\n  MD041: true\n"


def test_quoted_key_is_removed(tmp_path, github_output):
    src = _write(
        tmp_path / "src.yaml",
        '"outputFormatters": []\nconfig:\n  MD041: true\n',
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "config:\n  MD041: true\n"


def test_indentationless_sequence_value_is_fully_consumed(
    tmp_path, github_output
):
    # 列 0 の `- ` エントリはキーの値に属する正当な YAML（indentationless
    # block sequence）．キー行だけ落とすと壊れた YAML が残る．
    src = _write(
        tmp_path / "src.yaml",
        "outputFormatters:\n"
        "- [markdownlint-cli2-formatter-json]\n"
        "- [markdownlint-cli2-formatter-junit]\n"
        "config: {}\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "config: {}\n"


def test_dash_prefixed_plain_key_after_sequence_is_kept(tmp_path, github_output):
    # `-foo:`（ダッシュ直後に空白なし）は sequence エントリではなく通常のキー．
    src = _write(
        tmp_path / "src.yaml",
        "outputFormatters:\n- [x]\n-foo: 1\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "-foo: 1\n"


def test_uniformly_indented_root_mapping_is_handled(tmp_path, github_output):
    # root mapping 全体が一様にインデントされた正当な YAML でも除去できる．
    src = _write(
        tmp_path / "src.yaml",
        "  outputFormatters: []\n  config:\n    MD041: false\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "  config:\n    MD041: false\n"


def test_indented_root_with_sequence_entries_is_handled(tmp_path, github_output):
    src = _write(
        tmp_path / "src.yaml",
        "  outputFormatters:\n  - [x]\n  - [y]\n  config: {}\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "  config: {}\n"


def test_comment_lines_within_sequence_are_consumed(tmp_path, github_output):
    # 列 0 のコメント行が key 行直後やエントリ間にあっても値の消費を止めない．
    src = _write(
        tmp_path / "src.yaml",
        "outputFormatters:\n"
        "# formatter note\n"
        "- [x]\n"
        "# between entries\n"
        "- [y]\n"
        "config: {}\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "config: {}\n"


def test_utf8_bom_prefixed_src_is_accepted(tmp_path, github_output):
    src = tmp_path / "src.yaml"
    src.write_bytes(
        ("﻿" + "outputFormatters: []\nconfig: {}\n").encode("utf-8")
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_bytes() == b"config: {}\n"


def test_yaml11_scalars_survive_verbatim(tmp_path, github_output):
    # PyYAML（YAML 1.1）では on / yes が bool になるが，js-yaml 4 では文字列．
    # テキスト除去なら他行が保持され，型崩れが起きないことを固定する．
    src = _write(
        tmp_path / "src.yaml",
        "ignores:\n  - on\n  - yes\noutputFormatters: []\n",
    )

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.read_text(encoding="utf-8") == "ignores:\n  - on\n  - yes\n"


def test_runtime_name_is_unique_and_does_not_clobber_existing_file(
    tmp_path, github_output
):
    sentinel = _write(
        tmp_path / f"{RUNTIME_PREFIX}caller{RUNTIME_SUFFIX}", "caller-owned\n"
    )
    src = _write(tmp_path / "src.yaml", "outputFormatters: []\n")

    _MODULE.main([str(src)])

    runtime = Path(_outputs(github_output)["generated"])
    assert runtime.parent == tmp_path
    assert runtime.name.startswith(RUNTIME_PREFIX)
    assert runtime.name.endswith(RUNTIME_SUFFIX)
    assert runtime != sentinel
    assert sentinel.read_text(encoding="utf-8") == "caller-owned\n"


def test_removal_prints_single_warning_line(tmp_path, capsys, github_output):
    src = _write(tmp_path / "src.yaml", "outputFormatters: []\n")

    _MODULE.main([str(src)])

    out_lines = capsys.readouterr().out.strip().splitlines()
    assert len(out_lines) == 1
    assert out_lines[0].startswith("::warning::")
    assert "outputFormatters" in out_lines[0]


def test_flow_style_root_mapping_raises_value_error(tmp_path, github_output):
    src = _write(tmp_path / "src.yaml", "{outputFormatters: [], config: {}}\n")

    with pytest.raises(ValueError):
        _MODULE.main([str(src)])


def test_empty_src_file_passes_src_through(tmp_path, capsys, github_output):
    src = _write(tmp_path / "src.yaml", "")

    _MODULE.main([str(src)])

    assert list(tmp_path.glob(f"{RUNTIME_PREFIX}*")) == []
    assert _outputs(github_output) == {"config": str(src), "generated": ""}
    assert capsys.readouterr().out == ""


def test_missing_src_raises_file_not_found(tmp_path, github_output):
    with pytest.raises(FileNotFoundError):
        _MODULE.main([str(tmp_path / "no-such.yaml")])


def test_non_mapping_root_raises_type_error(tmp_path, github_output):
    src = _write(tmp_path / "src.yaml", "- not\n- a\n- mapping\n")

    with pytest.raises(TypeError):
        _MODULE.main([str(src)])


def test_missing_github_output_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    src = _write(tmp_path / "src.yaml", "config: {}\n")

    with pytest.raises(ValueError):
        _MODULE.main([str(src)])


@pytest.mark.parametrize("argv", [[], ["a", "b"]])
def test_wrong_argument_count_raises_value_error(argv, github_output):
    with pytest.raises(ValueError):
        _MODULE.main(argv)
