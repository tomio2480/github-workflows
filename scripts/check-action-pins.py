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
import json
import os
import re
import sys
import urllib.error
import urllib.request
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
#
# 値は引用符で囲まれうる（Issue #211）．YAML も GitHub Actions も
# `uses: "owner/repo@<SHA>"` を同じ値として解釈する．囲まれた形を収集できないと，
# SHA の一致検査にも版コメントの検査にも掛からない．開始と終了の引用符が対に
# なることを後方参照で求める．版コメントは引用符の外に置かれるため，閉じ引用符の
# 後ろで拾う．対にならない行は `collect_unrecognized` が拾う．YAML の二重引用符
# スカラーは複数行にまたがれるため，対にならないことを「不正な YAML だから
# 対象外」とは扱えない．
_USES_PIN = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<quote>[\"']?)"
    r"(?P<action>[\w.-]+/[\w.-]+(?:/[\w.-]+)*)"
    r"@(?P<sha>[0-9a-f]{40})"
    r"(?P=quote)"
    r"\s*(?:#\s*(?P<version>.*?))?\s*$"
)

# Dependabot が書き出すのは版だけである（`# v7.0.1`）．Issue #142 の決着により
# 中央の配布物は major のみ（`# v2`）を使うため，`vX` から `vX.Y.Z` まで許す．
_VERSION_COMMENT = re.compile(r"^v\d+(?:\.\d+){0,2}$")

# `docs/` は対象外とする（Issue #160）．`docs/development-notes.md` は
# Dependabot の挙動を示す証拠として PR #143 の差分を引いており，古い側の
# SHA と版が残っていることに意味がある．検査へ入れると直しようのない指摘に
# なる．オンボーディング手順（`docs/onboarding-new-repo.md`）も SHA を
# `git/refs/tags` から変数へ解決する形で，固定 SHA を書き下していない．
#
# 拡張子は `.yml` と `.yaml` の双方を見る（Issue #195）．GitHub は workflow を
# 双方の名前で認識し，composite action の定義も `action.yaml` が有効である．
# 片方だけを走査すると，もう片方の pin が検査を素通りする．
#
# composite action は `**` で受ける．任意のパスへ置けるため
# `.github/actions/<group>/<name>/action.yml` も有効な構成である．
# `*` は 1 階層しか一致せず，入れ子の pin が漏れる．`**` は 0 階層にも
# 一致するため，既存の 1 階層構成も同じパターンで覆える．
#
# ここでの走査範囲は `.github/dependabot.yml` の走査範囲と揃っていない
# （Issue #212）．同 file の `directories` は `/.github/actions/*` であり，
# Dependabot が使えるワイルドカードは `*` だけである．`*` は 1 階層しか
# 一致しないため，入れ子へ置いた composite action は **pin 検査には掛かるが
# 更新 PR は来ない** ．範囲を広く取るのは，検査から漏らさないためである．
# 追随されない pin を作らないよう，範囲のずれは
# `tests/python/test_action_pins.py` が検出する．
DEFAULT_GLOBS: tuple[str, ...] = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**/action.yml",
    ".github/actions/**/action.yaml",
    "templates/**/*.yml",
    "templates/**/*.yaml",
)


# SHA で pin されていない remote 参照を拾う．`_USES_PIN` は 40 桁 SHA の行しか
# 収集しないため，`@v7` のような浮動参照は pin としても違反としても現れず，
# 検査を素通りする．`AGENTS.md` は full commit SHA での pin を定めており，
# 素通りは規律違反を偽 green にする．
#
# 先頭 1 文字を `[A-Za-z0-9_-]` に限ることで `./` 始まりのローカル action を外す．
# ローカル参照は上流を持たないため pin の対象ではない．
#
# 引用符は action 名の手前で受ける（Issue #211）．先頭 1 文字の制限だけでは
# `uses: 'owner/repo@v7'` も同時に外れ，浮動参照が違反として報告されない．
# ref から引用符を除くのは，閉じ引用符を ref の一部として飲み込ませないためである．
# 飲み込むと `v7'` が SHA でもプレースホルダでもない別の文字列になり，
# 報告の中身が実際の ref とずれる．
_UNPINNED_USES = re.compile(
    r"^\s*(?:-\s*)?uses:\s*(?P<quote>[\"']?)"
    r"(?P<action>[A-Za-z0-9_-][\w.-]*/[\w.-]+(?:/[\w.-]+)*)"
    r"@(?P<ref>[^\s\"']+)"
    r"(?P=quote)"
)

# `uses` の鍵が現れる行を，書き方によらず広く拾う（Issue #211，PR #214）．
# 上の 2 つは 1 行のブロック形式しか解さない．YAML はほかの書き方も許すため，
# 値を次行へ置く形・flow mapping・コロン前に空白のある形は **どちらの正規表現にも
# 掛からず素通りする** ．収集できない形は，収集できないと報告する．
#
# 素通りを許さないだけでなく，これらの形は本リポジトリでは書かせない．
# Dependabot が書き換えるのは `uses: <action>@<SHA> # vX.Y.Z` の 1 行だけであり，
# 別の形へ置くと版コメントの規律（Issue #157）が成立しないためである．
#
# 鍵の位置を限る．行頭・リスト要素の先頭・flow mapping の内側だけを見る．
# 位置を限らないと `run: ./uses:x` のような本文まで拾う．
#
# flow mapping の 2 番目以降の鍵（`{name: x, uses: y}`）は `{` から `}` の手前
# までの範囲で探す．コンマの直後を無条件に見ると，コンマを挟んで `uses:` と
# 書いただけの説明文が違反になる．本リポジトリは `uses:` の書き方そのものを
# `description` や `name` で説明するため，実際に踏む．
_USES_KEY = re.compile(r"^\s*(?:-\s*)?(?:\{\s*)?uses\s*:|\{[^}]*\buses\s*:")

# 上流の SHA を持たない参照は pin の規律の対象外である．
_OUT_OF_SCOPE_USES = re.compile(r"uses\s*:\s*[\"']?(?:\./|docker://)")

# block scalar の開始行．中身は文字列であり，行頭に `uses:` と書かれていても
# mapping の鍵ではない．本リポジトリは `uses:` の書き方を説明する文書を持つため，
# 中身を鍵として拾うと正しいファイルが落ちる．
_BLOCK_SCALAR_HEADER = re.compile(r"^\s*(?:-\s*)?[^:#]+:\s*[|>][+-]?\d*\s*$")

# 配布テンプレの `@<SHA>` は未置換の目印である．山括弧を含む ref は git の
# 参照として成立しないため，浮動参照と区別できる．
_PLACEHOLDER_REF = re.compile(r"^<.+>$")

_SHA_REF = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Pin:
    """1 箇所の SHA pin．`version` は行末コメントが無ければ None."""

    action: str
    sha: str
    version: str | None
    location: str


@dataclass(frozen=True)
class UnpinnedRef:
    """SHA で pin されていない remote 参照 1 箇所．"""

    action: str
    ref: str
    location: str


@dataclass(frozen=True)
class UnrecognizedUse:
    """`uses` の鍵はあるが，収集できる形になっていない行 1 箇所．"""

    text: str
    location: str


def _strip_comment(line: str) -> str:
    """引用符の外にあるコメントを落とす．

    YAML の `#` は，行頭か空白の直後に来たときだけコメントを開く．
    `@v7#frag` のように直前が空白でない `#` は値の一部である．
    ここを取り違えると行の残りが消え，`uses` の鍵ごと見えなくなる．
    見えなくなった行は認識できない形としても報告されず，素通りする．
    """
    quote: str | None = None
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
            continue
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def scan_targets(root: Path, globs: Sequence[str] = DEFAULT_GLOBS) -> list[Path]:
    """走査対象のファイルを重複なく返す．"""
    seen: dict[Path, None] = {}
    for pattern in globs:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                seen.setdefault(path, None)
    return list(seen)


class UnreadableTarget(Exception):
    """走査対象を読めなかったことを，原因のファイル名付きで伝える．"""


def collect_pins(root: Path, globs: Sequence[str] = DEFAULT_GLOBS) -> list[Pin]:
    """root 配下の走査対象から SHA pin を収集する．"""
    pins: list[Pin] = []
    for path in scan_targets(root, globs):
        rel = path.relative_to(root).as_posix()
        # 生のトレースバックだけでは，caller リポジトリで原因のファイルを
        # 特定できない．握りつぶさず，どれが読めなかったかを添えて投げ直す．
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise UnreadableTarget(f"{rel}: 読み取りに失敗した（{error}）") from error
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


def collect_unpinned(
    root: Path, globs: Sequence[str] = DEFAULT_GLOBS
) -> list[UnpinnedRef]:
    """SHA で pin されていない remote 参照を収集する．

    ローカル action（`./` 始まり）と，配布テンプレの未置換プレースホルダ
    （`@<SHA>`）は対象外とする．前者は上流を持たず，後者は caller が置換して
    使う雛形であり，どちらも pin の規律の対象ではない．
    """
    unpinned: list[UnpinnedRef] = []
    for path in scan_targets(root, globs):
        rel = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise UnreadableTarget(f"{rel}: 読み取りに失敗した（{error}）") from error
        for lineno, line in enumerate(lines, start=1):
            matched = _UNPINNED_USES.match(line)
            if matched is None:
                continue
            ref = matched.group("ref")
            if _SHA_REF.match(ref) or _PLACEHOLDER_REF.match(ref):
                continue
            unpinned.append(
                UnpinnedRef(
                    action=matched.group("action"),
                    ref=ref,
                    location=f"{rel}:{lineno}",
                )
            )
    return unpinned


def collect_unrecognized(
    root: Path, globs: Sequence[str] = DEFAULT_GLOBS
) -> list[UnrecognizedUse]:
    """`uses` の鍵はあるが，収集できる形になっていない行を集める．

    `collect_pins` と `collect_unpinned` のどちらにも掛からない書き方は，
    pin としても違反としても現れない．素通りを違反として表に出す．

    コメント中の `uses:` は対象外とする．実ファイルの comment は `uses:` の
    書き方そのものを説明するため，拾うと正しいリポジトリが常に落ちる．
    """
    unrecognized: list[UnrecognizedUse] = []
    for path in scan_targets(root, globs):
        rel = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise UnreadableTarget(f"{rel}: 読み取りに失敗した（{error}）") from error
        # block scalar の中身を読み飛ばすため，開始行の字下げを覚えておく．
        # 抜けを判定できないと，以降のファイル全体が検査から外れる．
        # 素通りの範囲が 1 行から残り全体へ広がる．
        block_indent: int | None = None
        for lineno, line in enumerate(lines, start=1):
            indent = len(line) - len(line.lstrip())
            if block_indent is not None:
                if not line.strip() or indent > block_indent:
                    continue
                block_indent = None
            code = _strip_comment(line)
            is_block_header = bool(_BLOCK_SCALAR_HEADER.match(code))
            if _USES_KEY.search(code) and not _OUT_OF_SCOPE_USES.search(code):
                # 鍵そのものが block scalar で書かれていても見逃さない．
                # 中身を読み飛ばす扱いを，鍵の見逃しへ広げない．
                if not (_USES_PIN.match(line) or _UNPINNED_USES.match(line)):
                    unrecognized.append(
                        UnrecognizedUse(text=code.strip(), location=f"{rel}:{lineno}")
                    )
            if is_block_header:
                block_indent = indent
    return unrecognized


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


def _format_grouped(
    grouped: dict[str, dict[str, list[str]]],
    label: str,
    key_label: str = "{key}",
) -> list[str]:
    return [
        f"  {key_label.format(key=key)}: "
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
        # SHA は 7 桁へ短縮する．pytest 経路のメッセージと見え方を揃えるため．
        messages.extend(_format_grouped(inconsistent, "`# {value}`", "{key:.7}"))

    return messages


@dataclass(frozen=True)
class UpstreamFinding:
    """上流突合の結果 1 件．`level` は `error` か `warning`."""

    level: str
    message: str


def repository_of(action: str) -> str:
    """`uses:` の参照から問い合わせ先の repo を取り出す．

    composite action はサブパス付きで書かれる．
    `owner/repo/.github/actions/name` の repo は `owner/repo` である．
    """
    return "/".join(action.split("/")[:2])


def is_moving_tag(version: str) -> bool:
    """版コメントが可動タグかどうかを返す．

    `v2`・`v2.19` のように patch まで書かれていないタグは，リリースのたびに
    先へ動く．`v2.19.5` のように完全に書かれたタグは動かない．
    Issue #142 の決着により，本リポジトリの配布物は major のみを使う．
    """
    return version.count(".") < 2


def verify_upstream(pins: Sequence[Pin], client) -> list[UpstreamFinding]:
    """pin を上流と突き合わせる．

    判定は 3 段である（Issue #200）．

    - SHA が上流に実在しない: error．
    - 版コメントの系譜に SHA が属さない: error．
    - 最新タグより古いだけ: warning．

    最新タグとの一致を error にすると，上流が patch を切った瞬間に全 caller が
    赤くなる．追随は Dependabot の担当領域のため warning にとどめる．
    """
    findings: list[UpstreamFinding] = []
    # 同じ SHA を何度も問い合わせない．caller は同じ action を複数箇所で参照する．
    existence: dict[tuple[str, str], bool] = {}

    for pin in pins:
        repo = repository_of(pin.action)

        key = (repo, pin.sha)
        if key not in existence:
            existence[key] = client.commit_exists(repo, pin.sha)
        if not existence[key]:
            findings.append(
                UpstreamFinding(
                    "error",
                    f"{pin.location}: {pin.action}@{pin.sha[:7]} は上流に実在しない．",
                )
            )
            continue

        # 版コメントが無い pin は内部整合の検査が既に落としている．重ねて報告しない．
        if pin.version is None:
            continue

        tagged = client.tag_sha(repo, pin.version)
        if tagged is None:
            findings.append(
                UpstreamFinding(
                    "error",
                    f"{pin.location}: タグ `{pin.version}` が {repo} に無い．",
                )
            )
            continue

        if is_moving_tag(pin.version):
            if not client.is_ancestor(repo, pin.sha, tagged):
                findings.append(
                    UpstreamFinding(
                        "error",
                        f"{pin.location}: {pin.sha[:7]} は `{pin.version}` の"
                        "系譜に属さない．別の系列の SHA を指している．",
                    )
                )
                continue
        elif tagged != pin.sha:
            findings.append(
                UpstreamFinding(
                    "error",
                    f"{pin.location}: `{pin.version}` は {tagged[:7]} を指すが，"
                    f"pin は {pin.sha[:7]} である．固定タグは動かない．",
                )
            )
            continue

        major = int(pin.version[1:].split(".")[0])
        latest = client.latest_tag(repo, major)
        if latest is None:
            continue
        latest_name, latest_sha = latest
        if latest_sha != pin.sha and client.is_ancestor(repo, pin.sha, latest_sha):
            current = client.tag_at(repo, pin.sha) or pin.sha[:7]
            findings.append(
                UpstreamFinding(
                    "warning",
                    f"{pin.location}: {current} で止まっている．"
                    f"上流の最新は {latest_name} である．",
                )
            )

    return findings


class UpstreamUnavailable(Exception):
    """上流へ問い合わせられなかったことを伝える．

    「実在しない」「タグが無い」と区別する．区別しないと，一過性の
    レート制限や 5xx が「pin が壊れている」という誤った診断になる．
    """


def _default_fetch(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    """GitHub API を 1 回叩く．404 は例外にせず status として返す．

    HTTP 応答が返らない事象（名前解決失敗・接続断・タイムアウト）は
    `URLError` になる．生の traceback では「到達できなかった」ことが
    利用者に伝わらないため，呼び出し側（`_get`）で包み直す．
    """
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class GitHubUpstream:
    """GitHub REST API へ問い合わせる `verify_upstream` の相手方．

    pytest からは使わない．ネットワークを要するため，CI 層（`GITHUB_TOKEN` を
    持つ層）でだけ組み立てる．判定そのものは `verify_upstream` 側にある．
    """

    def __init__(
        self,
        token: str | None = None,
        api: str = "https://api.github.com",
        fetch=_default_fetch,
    ) -> None:
        self._api = api.rstrip("/")
        self._fetch = fetch
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "check-action-pins",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._tag_cache: dict[str, dict[str, str]] = {}
        self._repo_cache: dict[str, bool] = {}

    def _get(self, path: str) -> tuple[int, object]:
        try:
            status, body = self._fetch(f"{self._api}{path}", dict(self._headers))
        except (urllib.error.URLError, OSError) as error:
            raise UpstreamUnavailable(
                f"{path}: 上流へ問い合わせられなかった（{error}）"
            ) from error
        if not body:
            return status, None
        try:
            return status, json.loads(body)
        except json.JSONDecodeError:
            return status, None

    def commit_exists(self, repo: str, sha: str) -> bool:
        """SHA が上流に実在するかを返す．

        403（レート制限）や 5xx を False へ丸めない．一過性の障害が
        「pin が壊れている」という誤った error になるためである．

        404 も一律には読まない．GitHub は権限の無い private resource にも 404 を
        返す．caller が渡す repository-scoped の `GITHUB_TOKEN` では，別
        repository の private action を読めないことがある．そこで repository 自体を
        読めるかを確かめ，読めないなら「確かめられなかった」として扱う．
        読めるなら，commit の 404 は本当に実在しないことを意味する．
        """
        path = f"/repos/{repo}/commits/{sha}"
        status, _ = self._get(path)
        if status == 200:
            return True
        if status == 404:
            if not self._repo_accessible(repo):
                raise UpstreamUnavailable(
                    f"{repo}: repository を読めない．private な参照であれば，"
                    "その repository を読める token が要る．"
                )
            return False
        raise UpstreamUnavailable(f"{path}: 実在を確かめられなかった（HTTP {status}）")

    def _repo_accessible(self, repo: str) -> bool:
        """repository 自体を読めるかを返す．repo ごとに 1 度だけ引く．

        404 だけが「読めない」を意味する．403 や 5xx を「読めない」へ丸めない．
        落とす方向は同じでも診断が変わる．「private なら token が要る」という
        案内は，実際には再実行すれば直る場面で誤誘導になる．
        `commit_exists` が掲げる原則を，可視性確認の側も守る．
        """
        if repo in self._repo_cache:
            return self._repo_cache[repo]
        path = f"/repos/{repo}"
        status, _ = self._get(path)
        if status not in (200, 404):
            raise UpstreamUnavailable(
                f"{path}: repository を確かめられなかった（HTTP {status}）"
            )
        accessible = status == 200
        self._repo_cache[repo] = accessible
        return accessible

    def _tags(self, repo: str) -> dict[str, str]:
        """タグ名から commit SHA への対応を返す．repo ごとに 1 度だけ引く．"""
        if repo in self._tag_cache:
            return self._tag_cache[repo]
        tags: dict[str, str] = {}
        page = 1
        while True:
            path = f"/repos/{repo}/tags?per_page=100&page={page}"
            status, payload = self._get(path)
            # 失敗を空の結果としてキャッシュしない．一過性のレート制限や 5xx で
            # 空を覚えると，以降その repo の pin がすべて「タグが無い」という
            # 誤った error になる．1 回の障害が実行全体を汚す．
            if status != 200:
                raise UpstreamUnavailable(
                    f"{path}: タグ一覧を取得できなかった（HTTP {status}）"
                )
            if not isinstance(payload, list) or not payload:
                break
            for entry in payload:
                name = entry.get("name")
                sha = (entry.get("commit") or {}).get("sha")
                if name and sha:
                    tags[name] = sha
            if len(payload) < 100:
                break
            page += 1
        self._tag_cache[repo] = tags
        return tags

    def tag_sha(self, repo: str, tag: str) -> str | None:
        return self._tags(repo).get(tag)

    def tag_at(self, repo: str, sha: str) -> str | None:
        """当該 commit を指す，完全に書かれたタグ名を返す．"""
        fully = [
            name
            for name, tagged in self._tags(repo).items()
            if tagged == sha and _FULL_VERSION.match(name)
        ]
        return sorted(fully, key=_version_key)[-1] if fully else None

    def latest_tag(self, repo: str, major: int) -> tuple[str, str] | None:
        """当該 major で最も新しい，完全に書かれたタグを返す．"""
        fully = {
            name: sha
            for name, sha in self._tags(repo).items()
            if _FULL_VERSION.match(name) and name[1:].split(".")[0] == str(major)
        }
        if not fully:
            return None
        newest = max(fully, key=_version_key)
        return newest, fully[newest]

    def is_ancestor(self, repo: str, ancestor: str, descendant: str) -> bool:
        """`ancestor` が `descendant` の祖先か同一かを返す．

        compare の `base...head` は，head が base より後ろにあるとき `behind`
        を返す．base を子孫，head を祖先に置いて判定する．

        確かめられなかったことを False へ丸めない．丸めると帰結が 2 つ生じ，
        いずれも悪い．可動タグの判定では「系譜に属さない」という誤った error に
        なる．古さの判定では条件式が偽になり，本来出るべき warning が黙って
        消える．後者は 0 error のまま緑で終わるため，問い合わせに失敗したこと
        自体が見えなくなる．
        """
        if ancestor == descendant:
            return True
        path = f"/repos/{repo}/compare/{descendant}...{ancestor}"
        status, payload = self._get(path)
        if status != 200 or not isinstance(payload, dict):
            raise UpstreamUnavailable(
                f"{path}: 祖先関係を確かめられなかった（HTTP {status}）"
            )
        return payload.get("status") in {"identical", "behind"}


def _version_key(name: str) -> list[int]:
    return [int(part) for part in name[1:].split(".")]


_FULL_VERSION = re.compile(r"^v\d+\.\d+\.\d+$")


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
    parser.add_argument(
        "--verify-upstream",
        action="store_true",
        help="SHA の実在と版コメントの系譜を上流へ問い合わせる（ネットワークを要する）",
    )
    parser.add_argument(
        "--api",
        default="https://api.github.com",
        help="上流突合の問い合わせ先（既定は GitHub の公開 API）",
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

    # 走査対象が 0 件なら，pin の有無を論じる以前に読めていない．
    # `Path.glob()` は存在しないディレクトリでも例外を出さず空を返すため，
    # root の指定ミスがここまで素通りする．`--allow-empty` でも緩めない．
    # 「pin が 0 件」と「そもそも 1 つも読んでいない」は別の事象である．
    if not targets:
        print(
            f"走査対象が 0 件だった（root: {args.root}）．root か glob の指定が"
            "実態と合っていない．--allow-empty はこの状態を許さない．",
            file=sys.stderr,
        )
        return 1

    try:
        pins = collect_pins(args.root, globs)
    except UnreadableTarget as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"collected pins: {len(pins)}", flush=True)

    # 浮動参照は `--allow-empty` によらず落とす．`AGENTS.md` は full commit SHA
    # での pin を定めており，`@v7` のような参照は規律違反である．
    # ここを緩めると「pin が 0 件だから空扱いで緑」という抜け道ができ，
    # 対象ファイルも action も存在するのに違反が偽 green になる．
    try:
        unpinned = collect_unpinned(args.root, globs)
    except UnreadableTarget as error:
        print(str(error), file=sys.stderr)
        return 1
    if unpinned:
        print(
            "\n".join(
                [
                    "SHA で pin されていない remote 参照がある．"
                    "full commit SHA で pin すること．",
                    *[
                        f"  {ref.location}: {ref.action}@{ref.ref}"
                        for ref in unpinned
                    ],
                ]
            ),
            file=sys.stderr,
        )
        return 1

    # 認識できない形も `--allow-empty` によらず落とす．収集できないまま通すと，
    # そこに書かれた pin はどの検査にも掛からない．偽 green の経路である．
    try:
        unrecognized = collect_unrecognized(args.root, globs)
    except UnreadableTarget as error:
        print(str(error), file=sys.stderr)
        return 1
    if unrecognized:
        print(
            "\n".join(
                [
                    "収集できない形で `uses` が書かれている．"
                    "`uses: <action>@<SHA> # vX.Y.Z` の 1 行へ揃えること．"
                    "Dependabot が書き換えるのはこの形だけである（Issue #157）．",
                    *[
                        f"  {item.location}: {item.text}"
                        for item in unrecognized
                    ],
                ]
            ),
            file=sys.stderr,
        )
        return 1

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

    if not args.verify_upstream:
        return 0

    # token が無くても動くが，未認証はレート制限が厳しい．CI では GITHUB_TOKEN を渡す．
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print(
            "警告: GITHUB_TOKEN が無い．未認証で問い合わせるためレート制限が厳しい．",
            file=sys.stderr,
        )
    try:
        findings = verify_upstream(pins, GitHubUpstream(token=token, api=args.api))
    except UpstreamUnavailable as error:
        # 検査不能を「pin が壊れている」と report しない．落とすのは同じでも，
        # 診断が違えば利用者の次の一手が変わる（再実行か，pin の修正か）．
        print(f"上流突合を完了できなかった: {error}", file=sys.stderr)
        return 1

    errors = [finding for finding in findings if finding.level == "error"]
    warnings = [finding for finding in findings if finding.level == "warning"]

    # 警告は追随の督促であり落とさない．Dependabot の担当領域のためである．
    # ただし黙らせない．緑のまま古い pin が残り続ける状態を可視化する．
    for finding in warnings:
        print(f"warning: {finding.message}", flush=True)
    print(f"upstream: {len(errors)} error(s), {len(warnings)} warning(s)", flush=True)

    if errors:
        print(
            "\n".join(f"{finding.message}" for finding in errors),
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
