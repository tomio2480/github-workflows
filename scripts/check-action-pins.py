#!/usr/bin/env python3
"""third-party action の SHA pin と版コメントを検査する．

`tests/python/test_action_pins.py` は本リポジトリ自身の pin を検査してきた
（Issue #156・#157）．同じ検査は caller リポジトリでも要る．caller は中央の
pytest を走らせないため，判定を持ち出せる形にしておく必要がある．

本スクリプトは走査と判定だけを担う．root と glob を引数で受け取り，
`Path(__file__)` からリポジトリルートを推測しない．推測すると caller の
チェックアウトを渡しても中央の中身を読み，検査が空振りする．

検査はリポジトリ内部の一貫性に閉じる．当該 SHA が本当に `v7.0.1` かは上流へ
問い合わせないと分からないが，ここではネットワークへ依存させない．
上流との突合は CI 側（`GITHUB_TOKEN` を持つ層）の責務とする．

終了コードは違反なしで 0，違反ありで 1 とする．
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


# `uses: owner/repo@<40 桁 SHA>` と，あれば行末の版コメントを拾う．
# ローカル action（`./` 始まり）とタグ参照は対象外．タグ参照の禁止は
# 別の関心事であり本スクリプトでは扱わない．
#
# コメントは空白を含みうるため残り全体を捕捉する．版だけを `\S+` で拾うと
# `# actions/checkout v7.0.1` の行がマッチせず，pin ごと収集から漏れる．
# 漏れた pin はどの検査にも掛からないため，検査が素通りする．
_USES_PIN = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<action>[\w.-]+/[\w.-]+(?:/[\w.-]+)*)"
    r"@(?P<sha>[0-9a-f]{40})"
    r"\s*(?:#\s*(?P<version>.*?))?\s*$"
)

# Dependabot が書き出すのは版だけである（`# v7.0.1`）．Issue #142 の決着により
# 中央の配布物は major のみ（`# v2`）を使うため，`vX` から `vX.Y.Z` まで許す．
_VERSION_COMMENT = re.compile(r"^v\d+(?:\.\d+){0,2}$")

# `docs/` は対象外とする（Issue #160）．`docs/development-notes.md` は
# Dependabot の挙動を示す証拠として古い側の SHA と版を引いており，検査へ
# 入れると直しようのない指摘になる．
DEFAULT_GLOBS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/actions/*/action.yml",
    "templates/**/*.yml",
)


@dataclass(frozen=True)
class Pin:
    """1 箇所の SHA pin．`version` は行末コメントが無ければ None."""

    action: str
    sha: str
    version: str | None
    location: str


def scan_targets(root: Path, globs: Sequence[str] = DEFAULT_GLOBS) -> list[Path]:
    """走査対象のファイルを重複なく返す．"""
    seen: dict[Path, None] = {}
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                seen.setdefault(path, None)
    return list(seen)


def collect_pins(root: Path, globs: Sequence[str] = DEFAULT_GLOBS) -> list[Pin]:
    """root 配下の走査対象から SHA pin を収集する．"""
    pins: list[Pin] = []
    for path in scan_targets(root, globs):
        rel = path.relative_to(root).as_posix()
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            matched = _USES_PIN.match(line)
            if matched is None:
                continue
            pins.append(
                Pin(
                    action=matched.group("action"),
                    sha=matched.group("sha"),
                    version=matched.group("version"),
                    location=f"{rel}:{lineno}",
                )
            )
    return pins


def divergent_shas(pins: Sequence[Pin]) -> dict[str, dict[str, list[str]]]:
    """同じ action が 2 つ以上の SHA を指している箇所を返す．"""
    by_action: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for pin in pins:
        by_action[pin.action][pin.sha].append(pin.location)
    return {
        action: {sha: locations for sha, locations in shas.items()}
        for action, shas in by_action.items()
        if len(shas) > 1
    }


def pins_without_version(pins: Sequence[Pin]) -> list[Pin]:
    """行末の版コメントを持たない pin を返す．

    Dependabot が書き換えるのは SHA と同じ行のコメントだけである．
    直上行へ置くと SHA だけが更新され，版表記が古いまま残る（Issue #157）．
    """
    return [pin for pin in pins if pin.version is None]


def pins_with_malformed_version(pins: Sequence[Pin]) -> list[Pin]:
    """版コメントが `vX`〜`vX.Y.Z` の形になっていない pin を返す．"""
    return [
        pin
        for pin in pins
        if pin.version is not None and not _VERSION_COMMENT.match(pin.version)
    ]


def inconsistent_versions(pins: Sequence[Pin]) -> dict[str, dict[str, list[str]]]:
    """同じ SHA へ 2 通りの版表記が書かれている箇所を返す．"""
    by_sha: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for pin in pins:
        if pin.version is not None:
            by_sha[pin.sha][pin.version].append(pin.location)
    return {
        sha: {version: locations for version, locations in versions.items()}
        for sha, versions in by_sha.items()
        if len(versions) > 1
    }


def _format_grouped(grouped: dict[str, dict[str, list[str]]], label: str) -> list[str]:
    return [
        f"  {key}: "
        + " / ".join(
            f"{label.format(value=value)} ({', '.join(locations)})"
            for value, locations in sorted(entries.items())
        )
        for key, entries in sorted(grouped.items())
    ]


def find_violations(pins: Sequence[Pin]) -> list[str]:
    """検査結果を人が読める行の並びで返す．違反が無ければ空を返す．"""
    messages: list[str] = []

    divergent = divergent_shas(pins)
    if divergent:
        messages.append(
            "同じ action が複数の SHA へ pin されている．"
            "配布物は Dependabot の走査対象外のため取り残されやすい．"
        )
        messages.extend(_format_grouped(divergent, "{value:.7}"))

    missing = pins_without_version(pins)
    if missing:
        messages.append(
            "行末の版コメントが無い pin がある．"
            "`uses: <action>@<SHA> # vX.Y.Z` の形へ揃えること．"
            "直上行のコメントは Dependabot が更新しない（Issue #157）．"
        )
        messages.extend(
            f"  {pin.location}: {pin.action}@{pin.sha[:7]}" for pin in missing
        )

    malformed = pins_with_malformed_version(pins)
    if malformed:
        messages.append(
            "版コメントが版だけの形になっていない．"
            "Dependabot の出力（`# v7.0.1`）へ合わせること．"
        )
        messages.extend(f"  {pin.location}: `# {pin.version}`" for pin in malformed)

    inconsistent = inconsistent_versions(pins)
    if inconsistent:
        messages.append("同じ SHA へ異なる版コメントが書かれている．どちらかが誤りである．")
        messages.extend(_format_grouped(inconsistent, "`# {value}`"))

    return messages


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="走査の起点（既定はカレントディレクトリ）",
    )
    parser.add_argument(
        "--glob",
        dest="globs",
        action="append",
        default=None,
        help="走査対象の glob（繰り返し指定可．既定は配布物と workflow）",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="pin を 1 件も持たないリポジトリを成功として扱う",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    globs = tuple(args.globs) if args.globs else DEFAULT_GLOBS

    targets = scan_targets(args.root, globs)
    # 何を検査したかをログへ残す．成功時に無出力だと，走査が空振りした結果と
    # 区別が付かない（`github-dev` Skill「検査対象をログへ残す」）．
    print(f"targets (action pins): {len(targets)} file(s)", flush=True)
    for path in targets:
        print(f"  {path.relative_to(args.root).as_posix()}", flush=True)

    pins = collect_pins(args.root, globs)
    print(f"collected pins: {len(pins)}", flush=True)

    if not pins and not args.allow_empty:
        print(
            "SHA pin を 1 件も収集できなかった．走査 glob か正規表現が実態と"
            "合っていない可能性がある．偽 green を避けるため失敗させる．"
            "pin を持たないリポジトリでは --allow-empty を付けること．",
            file=sys.stderr,
        )
        return 1

    violations = find_violations(pins)
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
