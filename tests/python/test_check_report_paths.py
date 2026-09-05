"""scripts/check-report-paths.py の単体テスト．

textlint の checkstyle 出力は絶対パスを書く．集計側は workspace を prefix
として剥がして相対化する．剥がせなかったパスは対象一覧と一致せず，指摘が
黙って捨てられて 0 終了する（Issue #169 のレビュー指摘）．
剥がせない絶対パスがあれば失敗させ，沈黙を止める．
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-report-paths.py"

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<checkstyle version="4.3">
{files}
</checkstyle>
"""

FILE = '<file name="{name}"><error line="1" column="1" severity="error" '\
       'message="m" source="r" /></file>'


def write_report(tmp_path: Path, names: list[str]) -> Path:
    report = tmp_path / "textlint-report.xml"
    body = "\n".join(FILE.format(name=n) for n in names)
    report.write_text(TEMPLATE.format(files=body), encoding="utf-8")
    return report


def run(report: Path, workspace: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(report), workspace],
        capture_output=True,
        text=True,
    )


def test_accepts_paths_under_the_workspace(tmp_path: Path) -> None:
    report = write_report(tmp_path, ["C:/tmp/mirror/docs/a.md"])

    result = run(report, "C:/tmp/mirror")

    assert result.returncode == 0, result.stderr


def test_accepts_a_relative_path(tmp_path: Path) -> None:
    """markdownlint は相対で書く．剥がす対象ではない．"""
    report = write_report(tmp_path, ["docs/a.md"])

    result = run(report, "C:/tmp/mirror")

    assert result.returncode == 0, result.stderr


def test_accepts_a_backslash_spelling(tmp_path: Path) -> None:
    report = write_report(tmp_path, ["C:\\tmp\\mirror\\docs\\a.md"])

    result = run(report, "C:/tmp/mirror")

    assert result.returncode == 0, result.stderr


def test_rejects_an_absolute_path_outside_the_workspace(tmp_path: Path) -> None:
    report = write_report(tmp_path, ["C:/elsewhere/docs/a.md"])

    result = run(report, "C:/tmp/mirror")

    assert result.returncode != 0
    assert "C:/elsewhere/docs/a.md" in result.stderr


def test_rejects_a_case_only_mismatch(tmp_path: Path) -> None:
    """大小文字だけ違う表記は prefix 比較で剥がれない．8.3 名も同じ構造．"""
    report = write_report(tmp_path, ["C:/TMP/MIRROR/docs/a.md"])

    result = run(report, "C:/tmp/mirror")

    assert result.returncode != 0


def test_accepts_an_empty_report(tmp_path: Path) -> None:
    report = tmp_path / "textlint-report.xml"
    report.write_text(
        '<?xml version="1.0" encoding="UTF-8"?><checkstyle version="4.3"></checkstyle>',
        encoding="utf-8",
    )

    result = run(report, "C:/tmp/mirror")

    assert result.returncode == 0, result.stderr


def test_accepts_a_missing_report(tmp_path: Path) -> None:
    result = run(tmp_path / "absent.xml", "C:/tmp/mirror")

    assert result.returncode == 0, result.stderr


def test_fails_on_a_malformed_report(tmp_path: Path) -> None:
    """壊れたレポートを黙って通すと，件数 0 が実態と切り離される．"""
    report = tmp_path / "textlint-report.xml"
    report.write_text("<checkstyle>", encoding="utf-8")

    result = run(report, "C:/tmp/mirror")

    assert result.returncode != 0
