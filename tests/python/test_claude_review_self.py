"""中央リポジトリ自身の Claude レビュー導線に対する回帰テスト．

Issue #140 では，中央リポジトリの PR コメントで `@claude` をメンションしても
Actions run が起動しなかった．`.github/workflows/claude-review.yml` は
`workflow_call` 専用であり，`issue_comment` を受ける caller は
`templates/` 側にしか存在しなかったためである．

中央専用の self-caller を `.github/workflows/claude-review-self.yml` へ置き，
reusable workflow をローカル呼び出しする形で解決した．self-caller は配布する
caller テンプレートと同じ構造を保つ必要がある．ずれると，中央で通った設定が
caller で通らない（またはその逆）状態が生じ，中央をドッグフーディングの場と
して使えなくなる．ここではその同型性と，Issue #140 が挙げた制約を検証する．
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SELF_CALLER = _REPO_ROOT / ".github/workflows/claude-review-self.yml"
_TEMPLATE_CALLER = _REPO_ROOT / "templates/.github/workflows/claude-review.yml"
_REUSABLE = _REPO_ROOT / ".github/workflows/claude-review.yml"

# ローカル呼び出しの参照先．`@<SHA>` pin ではなく相対パスを使う点だけが
# caller テンプレートとの差分である．
_LOCAL_CALL = "./.github/workflows/claude-review.yml"

# PyYAML は YAML 1.1 として読むため，`on:` が真偽値 True のキーになる．
_ON_KEY = True


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _central_workflows(directory: Path | None = None) -> list[Path]:
    """workflow ファイルを列挙する．

    GitHub は `.yml` と `.yaml` の双方を workflow として認識する．片方だけを
    走査すると，もう片方で足された workflow が検査を素通りする．

    `directory` は検査の自己テスト用に差し替える．既定は中央リポジトリの
    `.github/workflows/` である．
    """
    target = directory if directory is not None else _REPO_ROOT / ".github/workflows"
    return sorted(
        path for suffix in ("*.yml", "*.yaml") for path in target.glob(suffix)
    )


def _triggers(workflow: dict, source: str) -> dict:
    """`on:` の内容を返す．PyYAML の真偽値化と生文字列の双方を受ける．

    `on:` が無いファイルは読み飛ばさず落とす．読み飛ばすと，本当は発火する
    workflow を見落としたまま「該当なし」で通ってしまう．
    """
    for key in (_ON_KEY, "on"):
        if key in workflow:
            return workflow[key]
    raise AssertionError(
        f"{source} に `on:` が無い．workflow でないファイルを "
        ".github/workflows/ へ置いた場合は，本テストの走査対象から外すこと．"
    )


@pytest.fixture(scope="module")
def self_caller() -> dict:
    assert _SELF_CALLER.exists(), (
        f"{_SELF_CALLER.relative_to(_REPO_ROOT).as_posix()} が無い．"
        "中央リポジトリ自身の `@claude` 起動経路が失われている（Issue #140）．"
    )
    return _load(_SELF_CALLER)


@pytest.fixture(scope="module")
def template_caller() -> dict:
    return _load(_TEMPLATE_CALLER)


def test_self_caller_calls_reusable_workflow_locally(self_caller: dict) -> None:
    """self-caller が中央の reusable workflow をローカル呼び出しすること．

    `OWNER/github-workflows/...@<SHA>` の形で自分自身を指すと，default branch
    に載るまで検証できない参照を持ち込むことになる．ローカル呼び出しなら
    呼び出し元と同じ ref の定義が使われる．
    """
    jobs = self_caller.get("jobs", {})
    uses = [job.get("uses") for job in jobs.values()]
    assert _LOCAL_CALL in uses, (
        f"self-caller が {_LOCAL_CALL} を呼んでいない．実際の uses: {uses}"
    )
    assert _REUSABLE.exists(), "ローカル呼び出しの参照先が存在しない．"


def test_self_caller_passes_oauth_token_secret(self_caller: dict) -> None:
    """reusable workflow が required 宣言している secret を渡すこと．

    渡し漏れは workflow の起動時エラーになる．caller テンプレートと同じ
    secret 名で受け渡す．
    """
    reusable = _load(_REUSABLE)
    required = set(
        _triggers(reusable, _REUSABLE.name)["workflow_call"]["secrets"]
    )

    for name, job in self_caller.get("jobs", {}).items():
        if job.get("uses") != _LOCAL_CALL:
            continue
        passed = set(job.get("secrets", {}))
        assert required <= passed, (
            f"job `{name}` が secret を渡し漏れている．"
            f"required={sorted(required)} / passed={sorted(passed)}"
        )
        return
    raise AssertionError("ローカル呼び出しの job が見つからない．")


def test_self_caller_triggers_match_template(
    self_caller: dict, template_caller: dict
) -> None:
    """trigger が caller テンプレートと一致すること．

    中央だけが別の trigger で動くと，caller で再現しない挙動を中央で見て
    しまう．テンプレートを正とし，中央はそれに従う．
    """
    assert _triggers(self_caller, _SELF_CALLER.name) == _triggers(
        template_caller, _TEMPLATE_CALLER.name
    ), (
        "self-caller の `on:` が caller テンプレートと食い違っている．"
    )


def test_self_caller_permissions_match_template(
    self_caller: dict, template_caller: dict
) -> None:
    """permissions が caller テンプレートと一致すること．

    reusable workflow 側の宣言は caller の付与を超えられない．中央とテンプレで
    付与が違うと，中央で通った権限設定が caller で不足する事態を招く．
    """
    assert self_caller.get("permissions") == template_caller.get("permissions"), (
        "self-caller の `permissions` が caller テンプレートと食い違っている．"
    )


def test_self_caller_does_not_grant_contents_write(self_caller: dict) -> None:
    """`contents: write` を付与しないこと（Issue #140 のスコープ外）．

    レビュー専用の導線であり，Claude にコード変更や push を許可しない．
    """
    permissions = self_caller.get("permissions", {})
    assert permissions.get("contents") != "write", (
        "self-caller が `contents: write` を付与している．"
        "レビュー専用の最小権限を維持すること．"
    )


def test_central_workflows_covers_both_yaml_extensions(tmp_path: Path) -> None:
    """列挙が `.yml` と `.yaml` の双方へ届くこと．

    片方だけを走査すると，もう片方で足されたコメント発火 workflow を
    見落としたまま「二重起動なし」で通る．走査の穴そのものを検査する．
    """
    (tmp_path / "a.yml").write_text("on: push\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("on: push\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("workflow ではない\n", encoding="utf-8")

    names = {path.name for path in _central_workflows(tmp_path)}
    assert names == {"a.yml", "b.yaml"}, f"列挙が想定と違う: {sorted(names)}"


def test_only_one_central_workflow_triggers_on_comments() -> None:
    """コメントで発火する中央 workflow が 1 つだけであること．

    Issue #140 は「中央 direct trigger と caller 経由で二重起動しない構成」を
    受け入れ条件に挙げている．中央へ caller を増やすと同じメンションで 2 件の
    run が起きる．新設時にここで気づけるようにする．
    """
    comment_triggers = {"issue_comment", "pull_request_review_comment"}
    firing = []
    for path in _central_workflows():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        triggers = _triggers(_load(path), rel)
        if not isinstance(triggers, dict):
            continue
        if comment_triggers & set(triggers):
            firing.append(rel)

    assert firing == [".github/workflows/claude-review-self.yml"], (
        "コメントで発火する中央 workflow が想定と違う．"
        f"二重起動していないか確認すること．検出: {firing}"
    )
