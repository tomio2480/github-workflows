#!/usr/bin/env python3
"""markdownlint-cli2 config から outputFormatters を除去した runtime config を生成する．

composite action は cli2 の既定 formatter 出力（`path:line[:col] RULE 説明`）に
依存する（reviewdog への errorformat 入力と summary 集計の 2 箇所）．
caller config が outputFormatters を定義すると既定 formatter は置き換えられ
（併存しない），lint が走って違反があっても inline・summary とも 0 件になる
（Issue #122）．本スクリプトはキーを除去して既定出力を守り，除去した事実を
Actions アノテーション（::warning::）で caller に知らせる．

引数は 1（src）．環境変数 GITHUB_OUTPUT へ `config=<採用パス>` と
`generated=<生成パス（生成時のみ）>` を追記する．src に outputFormatters
キーが無いときは何も生成せず src を採用する（パススルー）．これにより
outputFormatters を使わない caller の挙動は完全に不変となる．
採用パスの分岐まで本スクリプトが担うことで，全経路を pytest で検証できる．

runtime ファイルは src と同じディレクトリへ生成する．cli2 は customRules /
markdownItPlugins 等の相対パスを config ファイルのディレクトリ基準で解決する
ため，別ディレクトリへ退避すると caller の独自ルールが読めなくなる（PR #129
の Codex レビュー指摘）．ファイル名は tempfile.mkstemp による一意名とし，
caller 所有の同名ファイルを上書きしない（同レビュー指摘）．suffix は cli2 の
--config が受理する規約（`.markdownlint-cli2.yaml` で終わる名前）に合わせる．
生成物の後始末は呼び出し側が `generated` output を使って行う．

除去はトップレベルキーのテキスト除去で行い，他の行はバイト単位で保持する．
PyYAML の safe_load（YAML 1.1）と cli2 の js-yaml 4（YAML 1.2 系）は
スカラー解釈が異なり，往復再シリアライズでは引用符なしの on / yes 等が
bool へ化けて lint 挙動が変わりうるためである（同レビュー指摘）．
PyYAML はキーの検出と root の型検証のみに使う．
キーがあるときは値を問わず除去する（cli2 は空リストでもキーの存在だけで
既定 formatter を置き換えるため）．
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
from typing import Sequence

import yaml

RUNTIME_PREFIX = ".gh-workflows-runtime-"
RUNTIME_SUFFIX = ".markdownlint-cli2.yaml"

# root インデント直後の outputFormatters キー．引用符付きキーも受ける．
_KEY_RE_TEMPLATE = r"(?P<quote>['\"]?)outputFormatters(?P=quote)\s*:"

# キーの値に属する継続行として消費する root インデント位置の block sequence
# エントリ（indentationless sequence．`- ` または `-` 単独）．`-foo:` の
# ようなダッシュ始まりの plain キーは該当しない（空白が続かないため）．
_SEQUENCE_ENTRY_RE = re.compile(r"^-(?:[ \t]|$)")

OUTPUT_FORMATTERS_WARNING = (
    "::warning::.markdownlint-cli2.yaml の 'outputFormatters' は既定 formatter を"
    "置き換え，PR への inline コメントと summary 集計が 0 件になるため除去しました．"
    "独自 formatter が必要な場合は本 action と別のワークフローで実行してください"
    "（docs/architecture.md 参照）．"
)


def _emit_outputs(config_path: str, generated_path: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        raise ValueError("GITHUB_OUTPUT environment variable is required")
    with open(github_output, "a", encoding="utf-8") as fp:
        fp.write(f"config={config_path}\n")
        fp.write(f"generated={generated_path}\n")


def _root_indent(lines: list[str]) -> str:
    """root mapping のインデント（最初の内容行の先頭空白）を返す．

    YAML は root mapping 全体を一様にインデントできるため，列 0 固定に
    しない（PR #129 レビュー対応）．空行・コメント行は読み飛ばす．
    """
    for line in lines:
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        return line[: len(line) - len(line.lstrip(" "))]
    return ""


def _remove_top_level_key(text: str) -> str | None:
    """root インデント位置の outputFormatters キー行とその継続行を落とす．

    継続行は「root インデントより深い行」・空行・コメント行（任意インデント）
    に加え，root インデント位置の block sequence エントリ
    （indentationless sequence）を含む．コメントの除去は runtime の意味を
    変えない．他の行はバイト単位で保持する．キー行を特定できなければ
    None を返す（flow style の root mapping 等．呼び出し側で fail-closed
    にする）．
    """
    lines = text.splitlines(keepends=True)
    indent = _root_indent(lines)
    key_re = re.compile("^" + re.escape(indent) + _KEY_RE_TEMPLATE)

    def consumable(line: str) -> bool:
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            return True
        if not line.startswith(indent):
            return False
        rest = line[len(indent):]
        if rest[:1] in (" ", "\t"):
            return True
        return bool(_SEQUENCE_ENTRY_RE.match(rest))

    kept: list[str] = []
    removed = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if not removed and key_re.match(line):
            removed = True
            index += 1
            while index < len(lines) and consumable(lines[index]):
                index += 1
            continue
        kept.append(line)
        index += 1
    if not removed:
        return None
    return "".join(kept)


def main(argv: Sequence[str]) -> None:
    if len(argv) != 1:
        raise ValueError(f"expected 1 argument (src), got {len(argv)}")
    src = argv[0]

    src_path = pathlib.Path(src)
    # utf-8-sig で BOM を落として読む．BOM 付き config でもキー行を列 0 で
    # 照合でき，生成物は BOM なしで書かれる（cli2 はどちらも受理する）．
    text = src_path.read_text(encoding="utf-8-sig")
    cfg = yaml.safe_load(text)
    if cfg is not None and not isinstance(cfg, dict):
        raise TypeError(
            f"markdownlint-cli2 config root must be a mapping, got {type(cfg).__name__}"
        )
    if cfg is None or "outputFormatters" not in cfg:
        # 空ファイルは「設定なし」，キー無しは通常設定．どちらもそのまま渡す．
        _emit_outputs(src, "")
        return

    stripped = _remove_top_level_key(text)
    if stripped is None:
        # 黙って往復再シリアライズへ落とすと型崩れの恐れがあるため fail-closed．
        raise ValueError(
            "outputFormatters is present but could not be removed textually; "
            "write the config in block style (one top-level key per line)"
        )

    # 生成物を parse し直し，除去が構造を壊していないことを検証する．
    # root のキー集合が「元 − outputFormatters」と一致しなければ，壊れた
    # runtime を黙って cli2 へ渡さず fail-closed にする（PR #129 レビュー対応）．
    expected_keys = {key for key in cfg if key != "outputFormatters"}
    try:
        stripped_cfg = yaml.safe_load(stripped)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"removing outputFormatters produced invalid YAML: {exc}"
        ) from exc
    actual_keys = set(stripped_cfg) if isinstance(stripped_cfg, dict) else set()
    if (stripped_cfg is not None and not isinstance(stripped_cfg, dict)) or (
        actual_keys != expected_keys
    ):
        raise ValueError(
            "removing outputFormatters altered other top-level keys; "
            "write the config in block style (one top-level key per line)"
        )
    print(OUTPUT_FORMATTERS_WARNING)

    fd, dest = tempfile.mkstemp(
        dir=src_path.parent, prefix=RUNTIME_PREFIX, suffix=RUNTIME_SUFFIX
    )
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as fp:
        fp.write(stripped)
    _emit_outputs(dest, dest)


if __name__ == "__main__":
    main(sys.argv[1:])
