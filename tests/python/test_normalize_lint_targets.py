"""scripts/normalize-lint-targets.py の単体テスト．

CRLF の作業ツリーでは textlint が行末の CR を文の字数へ数える（Issue #169）．
lint は複製の側へ掛けるため，複製の作り方が結果を決める．
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "normalize-lint-targets.py"


def run(targets: Path, src: Path, dest: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(targets), str(src), str(dest)],
        capture_output=True,
        text=True,
    )


def write_targets(tmp_path: Path, names: list[str]) -> Path:
    targets = tmp_path / "targets.txt"
    targets.write_text("\n".join(names) + "\n", encoding="utf-8")
    return targets


@pytest.fixture()
def tree(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    return src, dest


def test_converts_crlf_to_lf(tmp_path: Path, tree) -> None:
    src, dest = tree
    (src / "a.md").write_bytes(b"# a\r\n\r\nhon bun\r\n")

    result = run(write_targets(tmp_path, ["a.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert (dest / "a.md").read_bytes() == b"# a\n\nhon bun\n"


def test_keeps_a_lone_cr(tmp_path: Path, tree) -> None:
    """単独の CR は改行ではない．消すと行が連結され，指摘が消えたり増えたりする．"""
    src, dest = tree
    (src / "a.md").write_bytes(b"# a\r\n\r\nbefore\rafter\r\n")

    result = run(write_targets(tmp_path, ["a.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert (dest / "a.md").read_bytes() == b"# a\n\nbefore\rafter\n"


def test_keeps_a_file_without_a_trailing_newline(tmp_path: Path, tree) -> None:
    """末尾改行の有無は markdownlint の MD047 が見る．複製で足してはならない．"""
    src, dest = tree
    (src / "a.md").write_bytes(b"# a\r\nno trailing newline")

    result = run(write_targets(tmp_path, ["a.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert (dest / "a.md").read_bytes() == b"# a\nno trailing newline"


def test_preserves_the_relative_structure(tmp_path: Path, tree) -> None:
    """相対構造が崩れると突合が外れ，全指摘が黙って消える．"""
    src, dest = tree
    (src / "docs").mkdir()
    (src / "docs" / "nested.md").write_bytes(b"# nested\r\n")

    result = run(write_targets(tmp_path, ["docs/nested.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert (dest / "docs" / "nested.md").read_bytes() == b"# nested\n"


def test_keeps_a_name_with_leading_whitespace(tmp_path: Path, tree) -> None:
    src, dest = tree
    (src / " lead.md").write_bytes(b"# lead\r\n")

    result = run(write_targets(tmp_path, [" lead.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert (dest / " lead.md").read_bytes() == b"# lead\n"


def test_skips_a_deleted_target(tmp_path: Path, tree) -> None:
    """差分には削除済みファイルも入る．実体が無く glob も拾わない．"""
    src, dest = tree
    (src / "a.md").write_bytes(b"# a\n")

    result = run(write_targets(tmp_path, ["a.md", "gone.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1"
    assert not (dest / "gone.md").exists()


def test_reports_zero_when_nothing_exists(tmp_path: Path, tree) -> None:
    src, dest = tree

    result = run(write_targets(tmp_path, ["gone.md"]), src, dest)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"


def test_fails_when_a_target_escapes_the_source_root(tmp_path: Path, tree) -> None:
    """複製先を作業ツリー外へ広げない．"""
    src, dest = tree
    (src / "a.md").write_bytes(b"# a\n")

    result = run(write_targets(tmp_path, ["../outside.md"]), src, dest)

    assert result.returncode != 0
    assert "outside" in result.stderr
