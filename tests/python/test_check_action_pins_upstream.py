"""scripts/check-action-pins.py の上流突合に対する単体テスト．

内部整合の検査（`test_check_action_pins.py`）だけでは，pin が上流に実在するか，
版コメントが指す系譜に属するかを確かめられない．`tomio2480/settings` の 3 参照は
いずれも `# v2` と書きながら別々の commit を指していたが，action のパスが違う
ため内部整合では違反にならず exit 0 になった．

上流突合はネットワークを要する．pytest を外部へ依存させないため，問い合わせ先は
注入可能にし，本テストは偽の client を渡す．実際の HTTP 実装は CI 層で使う．

判定の政策は Issue #200 のとおり 3 段である．

| 判定 | 扱い |
| --- | --- |
| SHA が上流に実在しない | error |
| 版コメントの系譜に SHA が属さない | error |
| 最新タグより古い | warning |

「最新タグと一致するか」を error にすると，中央が patch を切った瞬間に全 caller
が赤くなる．Issue #142 が版コメントを major のみへ改めた狙いと衝突するため，
古さは Dependabot の担当領域として warning にとどめる．
"""

from __future__ import annotations

import importlib

import pytest


_MODULE = importlib.import_module("check-action-pins")

Pin = _MODULE.Pin

_OLD = "1111111111111111111111111111111111111111"
_TIP = "2222222222222222222222222222222222222222"
_ALIEN = "3333333333333333333333333333333333333333"

_REPO = "tomio2480/github-workflows"


class FakeUpstream:
    """上流の問い合わせ先を差し替える．

    `ancestors` は「タグの commit → その祖先とみなす SHA の集合」である．
    """

    def __init__(
        self,
        tags: dict[str, str] | None = None,
        ancestors: dict[str, set[str]] | None = None,
        known: set[str] | None = None,
    ) -> None:
        self.tags = tags if tags is not None else {}
        self.ancestors = ancestors if ancestors is not None else {}
        self.known = known if known is not None else set()
        self.calls: list[str] = []

    def commit_exists(self, repo: str, sha: str) -> bool:
        self.calls.append(f"commit_exists:{repo}:{sha}")
        return sha in self.known

    def tag_sha(self, repo: str, tag: str) -> str | None:
        self.calls.append(f"tag_sha:{repo}:{tag}")
        return self.tags.get(tag)

    def is_ancestor(self, repo: str, ancestor: str, descendant: str) -> bool:
        self.calls.append(f"is_ancestor:{repo}:{ancestor}:{descendant}")
        if ancestor == descendant:
            return True
        return ancestor in self.ancestors.get(descendant, set())

    def tag_at(self, repo: str, sha: str) -> str | None:
        self.calls.append(f"tag_at:{repo}:{sha}")
        fully = [
            name
            for name, tagged in self.tags.items()
            if tagged == sha and name.count(".") == 2
        ]
        return sorted(fully)[0] if fully else None

    def latest_tag(self, repo: str, major: int) -> tuple[str, str] | None:
        self.calls.append(f"latest_tag:{repo}:{major}")
        fully = {
            name: sha
            for name, sha in self.tags.items()
            if name.startswith(f"v{major}.") and name.count(".") == 2
        }
        if not fully:
            return None
        newest = max(fully, key=lambda n: [int(p) for p in n[1:].split(".")])
        return newest, fully[newest]


def levels(findings) -> list[str]:
    return [finding.level for finding in findings]


def test_repository_of_takes_the_first_two_path_segments() -> None:
    """`uses:` のサブパス付き参照から，問い合わせ先の repo を取り出すこと．"""
    assert (
        _MODULE.repository_of("tomio2480/github-workflows/.github/actions/markdown-lint")
        == "tomio2480/github-workflows"
    )
    assert _MODULE.repository_of("actions/checkout") == "actions/checkout"


def test_missing_commit_is_an_error() -> None:
    """上流に実在しない SHA は落とすこと（受け入れ条件）．"""
    pins = [Pin("actions/checkout", _ALIEN, "v7.0.1", "a.yml:1")]
    client = FakeUpstream(known=set(), tags={"v7.0.1": _TIP})

    findings = _MODULE.verify_upstream(pins, client)

    assert levels(findings) == ["error"]
    assert "実在しない" in findings[0].message
    assert "a.yml:1" in findings[0].message


def test_moving_tag_accepts_an_ancestor_of_the_tag() -> None:
    """`# v2` のような可動タグは，系譜に属していれば通すこと．

    中央が patch を切るたびに全 caller が赤くなるのを避けるためである．
    """
    pins = [Pin(_REPO, _OLD, "v2", "a.yml:1")]
    client = FakeUpstream(
        known={_OLD, _TIP},
        tags={"v2": _TIP, "v2.19.5": _TIP, "v2.15.1": _OLD},
        ancestors={_TIP: {_OLD}},
    )

    findings = _MODULE.verify_upstream(pins, client)

    assert "error" not in levels(findings)


def test_moving_tag_rejects_a_sha_outside_the_lineage() -> None:
    """系譜に属さない SHA は落とすこと（`# v2` と書いて v1 の SHA 等）．"""
    pins = [Pin(_REPO, _ALIEN, "v2", "a.yml:1")]
    client = FakeUpstream(known={_ALIEN, _TIP}, tags={"v2": _TIP}, ancestors={})

    findings = _MODULE.verify_upstream(pins, client)

    assert "error" in levels(findings)
    assert "系譜" in findings[0].message


def test_stale_pin_is_only_a_warning() -> None:
    """最新タグより古いだけの pin は落とさず警告にとどめること．

    追随は Dependabot の担当領域である．
    """
    pins = [Pin(_REPO, _OLD, "v2", "a.yml:1")]
    client = FakeUpstream(
        known={_OLD, _TIP},
        tags={"v2": _TIP, "v2.19.5": _TIP, "v2.15.1": _OLD},
        ancestors={_TIP: {_OLD}},
    )

    findings = _MODULE.verify_upstream(pins, client)

    assert levels(findings) == ["warning"]
    assert "v2.19.5" in findings[0].message
    assert "v2.15.1" in findings[0].message


def test_pin_at_the_tip_produces_no_finding() -> None:
    pins = [Pin(_REPO, _TIP, "v2", "a.yml:1")]
    client = FakeUpstream(
        known={_TIP},
        tags={"v2": _TIP, "v2.19.5": _TIP},
        ancestors={},
    )

    assert _MODULE.verify_upstream(pins, client) == []


def test_exact_version_must_point_at_the_same_commit() -> None:
    """`# v7.0.1` のような固定タグは，同じ commit を指していること．

    固定タグは動かない．祖先であることを許すと，別リリースの SHA へ
    誤った版を書いた状態を見逃す．
    """
    pins = [Pin("actions/checkout", _OLD, "v7.0.1", "a.yml:1")]
    client = FakeUpstream(
        known={_OLD, _TIP},
        tags={"v7.0.1": _TIP},
        ancestors={_TIP: {_OLD}},
    )

    findings = _MODULE.verify_upstream(pins, client)

    assert "error" in levels(findings)


def test_exact_version_at_the_same_commit_passes() -> None:
    pins = [Pin("actions/checkout", _TIP, "v7.0.1", "a.yml:1")]
    client = FakeUpstream(known={_TIP}, tags={"v7.0.1": _TIP})

    assert _MODULE.verify_upstream(pins, client) == []


def test_unknown_tag_is_an_error() -> None:
    """版コメントに対応するタグが上流に無ければ落とすこと．"""
    pins = [Pin(_REPO, _TIP, "v9", "a.yml:1")]
    client = FakeUpstream(known={_TIP}, tags={"v2": _TIP})

    findings = _MODULE.verify_upstream(pins, client)

    assert "error" in levels(findings)
    assert "v9" in findings[0].message


def test_pins_without_version_are_skipped_by_upstream_check() -> None:
    """版コメントの無い pin は内部整合の検査が既に落としている．

    上流突合では重ねて報告せず，実在の確認だけを行う．
    """
    pins = [Pin("actions/checkout", _TIP, None, "a.yml:1")]
    client = FakeUpstream(known={_TIP}, tags={})

    assert _MODULE.verify_upstream(pins, client) == []


def test_each_commit_is_queried_once_per_sha() -> None:
    """同じ SHA を何度も問い合わせないこと．

    caller の workflow は同じ action を複数箇所で参照する．pin ごとに
    問い合わせると，API のレート制限を無駄に消費する．
    """
    pins = [
        Pin("actions/checkout", _TIP, "v7.0.1", "a.yml:1"),
        Pin("actions/checkout", _TIP, "v7.0.1", "b.yml:1"),
        Pin("actions/checkout", _TIP, "v7.0.1", "c.yml:1"),
    ]
    client = FakeUpstream(known={_TIP}, tags={"v7.0.1": _TIP})

    _MODULE.verify_upstream(pins, client)

    assert client.calls.count(f"commit_exists:actions/checkout:{_TIP}") == 1


@pytest.mark.parametrize(
    ("version", "moving"),
    [
        pytest.param("v2", True, id="major のみは可動"),
        pytest.param("v2.19", True, id="minor までは可動"),
        pytest.param("v2.19.5", False, id="patch まで書けば固定"),
    ],
)
def test_is_moving_tag_classifies_by_component_count(
    version: str, moving: bool
) -> None:
    assert _MODULE.is_moving_tag(version) is moving


class RecordingFetch:
    """`GitHubUpstream` の HTTP 呼び出しを差し替える．

    `responses` は URL の部分一致から `(status, body)` への対応である．
    """

    def __init__(self, responses: dict[str, tuple[int, bytes]]) -> None:
        self.responses = responses
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[int, bytes]:
        self.urls.append(url)
        self.headers.append(headers)
        for fragment, response in self.responses.items():
            if fragment in url:
                return response
        return 404, b"{}"


def tags_payload(entries: list[tuple[str, str]]) -> bytes:
    import json

    return json.dumps(
        [{"name": name, "commit": {"sha": sha}} for name, sha in entries]
    ).encode()


def test_client_asks_the_commit_endpoint_and_reads_the_status() -> None:
    """実在確認は commits エンドポイントの status で決めること．"""
    fetch = RecordingFetch({f"/repos/actions/checkout/commits/{_TIP}": (200, b"{}")})
    client = _MODULE.GitHubUpstream(token=None, fetch=fetch)

    assert client.commit_exists("actions/checkout", _TIP) is True
    assert client.commit_exists("actions/checkout", _ALIEN) is False
    assert fetch.urls[0].endswith(f"/repos/actions/checkout/commits/{_TIP}")


def test_client_sends_the_token_when_given() -> None:
    fetch = RecordingFetch({"/commits/": (200, b"{}")})
    client = _MODULE.GitHubUpstream(token="secret-value", fetch=fetch)

    client.commit_exists("actions/checkout", _TIP)

    assert fetch.headers[0]["Authorization"] == "Bearer secret-value"


def test_client_compares_descendant_against_ancestor_in_that_order() -> None:
    """compare は `base...head` で head が base の祖先なら `behind` を返す．

    base に子孫，head に祖先を置く．順序を逆にすると判定が反転する．
    """
    fetch = RecordingFetch({"/compare/": (200, b'{"status": "behind"}')})
    client = _MODULE.GitHubUpstream(token=None, fetch=fetch)

    assert client.is_ancestor(_REPO, _OLD, _TIP) is True
    assert fetch.urls[0].endswith(f"/compare/{_TIP}...{_OLD}")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        pytest.param("behind", True, id="祖先"),
        pytest.param("identical", True, id="同一"),
        pytest.param("ahead", False, id="子孫"),
        pytest.param("diverged", False, id="分岐"),
    ],
)
def test_client_maps_compare_status_to_ancestry(status: str, expected: bool) -> None:
    import json

    body = json.dumps({"status": status}).encode()
    client = _MODULE.GitHubUpstream(
        token=None, fetch=RecordingFetch({"/compare/": (200, body)})
    )

    assert client.is_ancestor(_REPO, _OLD, _TIP) is expected


def test_client_pages_through_tags_until_a_short_page() -> None:
    """タグは 100 件ずつ辿り，短いページで打ち切ること．"""
    page1 = tags_payload([(f"v2.0.{i}", f"{i:040d}") for i in range(100)])
    page2 = tags_payload([("v2.1.0", _TIP)])
    # 照合は `&page=N` で行う．`page=N` だけだと `per_page=100` の一部にも
    # 一致し，全ページが 1 ページ目の応答を返して無限ループになる．
    fetch = RecordingFetch({"&page=1": (200, page1), "&page=2": (200, page2)})
    client = _MODULE.GitHubUpstream(token=None, fetch=fetch)

    assert client.tag_sha(_REPO, "v2.1.0") == _TIP
    assert sum("/tags?" in url for url in fetch.urls) == 2


def test_client_asks_for_tags_only_once_per_repository() -> None:
    fetch = RecordingFetch({"/tags?": (200, tags_payload([("v2.1.0", _TIP)]))})
    client = _MODULE.GitHubUpstream(token=None, fetch=fetch)

    client.tag_sha(_REPO, "v2.1.0")
    client.tag_at(_REPO, _TIP)
    client.latest_tag(_REPO, 2)

    assert sum("/tags?" in url for url in fetch.urls) == 1


def test_client_does_not_cache_a_failed_tag_lookup() -> None:
    """タグの取得に失敗したら，空の結果をキャッシュしないこと．

    一過性のレート制限や 5xx で空をキャッシュすると，以降その repo の pin が
    すべて「タグが無い」という誤った error になる．1 回の障害が実行全体を汚す．
    """
    client = _MODULE.GitHubUpstream(
        token=None, fetch=RecordingFetch({"/tags?": (503, b"{}")})
    )

    with pytest.raises(_MODULE.UpstreamUnavailable):
        client.tag_sha(_REPO, "v2")

    # 復旧後は正しく引けること（失敗が固定化していないこと）．
    client._fetch = RecordingFetch({"/tags?": (200, tags_payload([("v2", _TIP)]))})
    assert client.tag_sha(_REPO, "v2") == _TIP


def test_client_reports_an_unreachable_upstream_clearly() -> None:
    """到達できない上流は，生の traceback でなく趣旨の伝わる例外にすること．"""

    def failing_fetch(url: str, headers: dict[str, str]):
        import urllib.error

        raise urllib.error.URLError("getaddrinfo failed")

    client = _MODULE.GitHubUpstream(token=None, fetch=failing_fetch)

    with pytest.raises(_MODULE.UpstreamUnavailable) as caught:
        client.commit_exists("actions/checkout", _TIP)

    assert "actions/checkout" in str(caught.value)
