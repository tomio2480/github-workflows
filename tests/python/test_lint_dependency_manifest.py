"""lint 依存を記す manifest の置き場所に対する回帰テスト．

GitHub は 2026 年 5 月下旬以降，一部の Dependabot PR を受け付けない．
github-actions 以外のエコシステムが `.github/` 配下を変える PR である．
更新の計算は済んでも，PR 作成 API が 400 を返して終わる
（dependabot/dependabot-core#15721）．npm manifest を action.yml の
隣へ置いた間も，2026 年 5 月中旬までは更新 PR が届いていた（#40・#47）．
失敗は 2026-05-25 の実行から始まった．

manifest は `.github/` の外へ置く．composite action と Dependabot が
同じ場所を指すかは，機械で確かめる．規律には頼らない．
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from typing import Any

import yaml


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEPENDABOT_CONFIG = _REPO_ROOT / ".github" / "dependabot.yml"
_ACTION_DIR = ".github/actions/markdown-lint"
_ACTION_PATH_EXPRESSION = "${{ github.action_path }}"


def _updates() -> list[dict[str, Any]]:
    document = yaml.safe_load(_DEPENDABOT_CONFIG.read_text(encoding="utf-8"))
    return list(document["updates"])


def _directories(update: dict[str, Any]) -> list[str]:
    directories = list(update.get("directories", []))
    if "directory" in update:
        directories.append(update["directory"])
    return directories


def _npm_directories() -> list[str]:
    return [
        directory
        for update in _updates()
        if update["package-ecosystem"] == "npm"
        for directory in _directories(update)
    ]


def test_only_github_actions_updates_reach_into_dot_github() -> None:
    """github-actions 以外の走査対象が `.github/` 配下に無いこと．

    配下へ置くと，Dependabot は更新を計算したうえで PR 作成だけが 400 で
    失敗する．失敗は Dependabot のジョブ側にしか残らず，PR が来ないという
    形でしか現れない．
    """
    offending = [
        f"{update['package-ecosystem']}: {directory}"
        for update in _updates()
        if update["package-ecosystem"] != "github-actions"
        for directory in _directories(update)
        if directory.strip("/").split("/")[0] == ".github"
    ]
    assert not offending, "\n".join(
        [
            "github-actions 以外のエコシステムが .github/ 配下を走査している．"
            "GitHub はその更新 PR を受け付けない（dependabot-core#15721）．",
            *[f"  {entry}" for entry in offending],
        ]
    )


def test_npm_update_directory_holds_the_lint_manifest() -> None:
    """npm の走査対象が 1 箇所で，lint 依存の manifest と lockfile を持つこと．"""
    directories = _npm_directories()
    assert len(directories) == 1, directories
    manifest_dir = _REPO_ROOT / directories[0].strip("/")
    assert (manifest_dir / "package.json").is_file()
    assert (manifest_dir / "package-lock.json").is_file()


def test_action_installs_from_the_npm_update_directory() -> None:
    """composite action が Dependabot の追う manifest から依存を導入すること．

    両者が別の場所を指すと，Dependabot の更新 PR は action の挙動を変えない．
    """
    action = yaml.safe_load(
        (_REPO_ROOT / _ACTION_DIR / "action.yml").read_text(encoding="utf-8")
    )
    step = next(
        step for step in action["runs"]["steps"] if step.get("id") == "lint_install"
    )
    value = step["env"]["MANIFEST_DIR"]
    assert value.startswith(_ACTION_PATH_EXPRESSION), value
    resolved = posixpath.normpath(
        "/" + _ACTION_DIR + value[len(_ACTION_PATH_EXPRESSION) :]
    )
    assert [resolved] == _npm_directories()
